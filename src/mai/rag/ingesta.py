"""Ingesta de las políticas: de PDF a fragmentos citables.

`Fragmento` se importa del dominio y no se define aquí. La dirección de la
dependencia importa: la ingesta es infraestructura —sabe de PDF, de ReportLab
y de expresiones regulares— y el fragmento citable es vocabulario del
problema. Que la infraestructura dependa del dominio es correcto; al revés,
no.

**No hay algoritmo de fragmentación aquí, y eso es la decisión.** Los cinco
documentos traen secciones numeradas —`3. Solicitud y aprobación`, `3.1.`,
`3.2.`— y esa numeración ya es la unidad de sentido: cada una es una regla
completa. Cortar por ventana fija de N caracteres partiría reglas a la mitad
(«la solicitud debe radicarse con | anticipación mínima de quince días») y
produciría fragmentos que responden a medias.

Y hay un segundo motivo, más importante: **el número de sección es la cita**.
`POL-GTH-01 §3.1` sale de la estructura del documento, no de una heurística,
así que es exacta y verificable por quien lea la respuesta. Con ventanas
fijas habría que inventar identificadores de fragmento que no significan nada
para una persona.

Se corta al nivel numerado más fino disponible: si una sección tiene
subsecciones, cada subsección es un fragmento; si no, lo es la sección
entera. Medido sobre el corpus: 37 secciones y 43 subsecciones producen unos
80 fragmentos de ~25 palabras.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mai.dominio.politicas import Fragmento

logger = logging.getLogger(__name__)

# El título de una sección empieza con letra. Sin esa exigencia, una fila de
# tabla como «1 al 20 de enero» o una cifra suelta se leerían como sección.
_SECCION = re.compile(r"^\s*(\d{1,2})\.\s+([^\W\d_].*)$")
_SUBSECCION = re.compile(r"^\s*(\d{1,2}\.\d{1,2})\.\s+([^\W\d_].*)$")

# Cabecera: «LA FORTUNA S.A. · Código POL-GTH-01 · Versión 3 · Vigente…»
_CODIGO = re.compile(r"C[óo]digo\s+([A-Z]{2,4}-[A-Z]{2,4}-\d{2,3})")
_VERSION = re.compile(r"Versi[óo]n\s+(\S+)")

LARGO_MINIMO_FRAGMENTO = 20


class ErrorDeIngesta(Exception):
    """No se pudo leer un documento de políticas."""


@dataclass(frozen=True)
class ReporteDeIngesta:
    """Qué entró, qué salió y qué se descartó. Nada desaparece en silencio."""

    documentos_leidos: int
    fragmentos: int
    descartados_por_cortos: int
    documentos_ilegibles: list[str]


def extraer_texto(ruta: Path) -> str:
    """Texto plano de un PDF, con los caracteres de control normalizados.

    ReportLab —el generador de estos documentos— representa la viñeta de las
    subsecciones con `\\x7f` (DEL). Sin normalizarlo, cualquier expresión
    regular que espere una viñeta no encuentra ni una subsección: medido, 0
    de 43. Se sustituye por espacio todo carácter de control salvo el salto
    de línea, que es lo que separa las secciones.

    Lanza `ErrorDeIngesta` si el archivo no se puede leer. Un PDF corrupto no
    puede tumbar la ingesta de los otros cuatro.
    """
    try:
        lector = PdfReader(str(ruta))
        crudo = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except (PdfReadError, OSError, ValueError) as error:
        raise ErrorDeIngesta(f"No se pudo leer «{ruta.name}»: {error}") from error

    return "".join(
        " " if unicodedata.category(c) == "Cc" and c != "\n" else c for c in crudo
    )


def leer_cabecera(texto: str, respaldo: str) -> tuple[str, str, str]:
    """Código, título y versión del documento, leídos de su propia cabecera.

    Se prefiere el contenido al nombre del archivo: si alguien renombra el
    PDF, las citas ya emitidas seguirían apuntando al código correcto. Si la
    cabecera no trae código, se usa `respaldo` —el nombre del archivo— antes
    que descartar el documento.
    """
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    titulo = lineas[0] if lineas else respaldo

    cabecera = "\n".join(lineas[:5])
    coincidencia = _CODIGO.search(cabecera)
    codigo = coincidencia.group(1) if coincidencia else respaldo

    version_encontrada = _VERSION.search(cabecera)
    version = version_encontrada.group(1) if version_encontrada else "sin versión"

    return codigo, titulo, version


def fragmentar(texto: str, codigo: str, titulo_documento: str, version: str) -> list[Fragmento]:
    """Parte el texto en fragmentos, uno por sección o subsección numerada.

    El texto anterior a la sección 1 —cabecera, título, vigencia— no produce
    fragmento: es metadato, no contenido consultable.

    Un fragmento más corto que `LARGO_MINIMO_FRAGMENTO` caracteres se
    descarta: son títulos de sección sin cuerpo propio, que solo añaden ruido
    a la búsqueda. El descarte se cuenta en el reporte, no se silencia.
    """
    fragmentos: list[Fragmento] = []
    seccion_actual: str | None = None
    titulo_actual = ""
    titulo_padre = ""
    acumulado: list[str] = []

    def cerrar() -> None:
        if seccion_actual is None:
            return
        cuerpo = " ".join(" ".join(acumulado).split())
        fragmentos.append(
            Fragmento(
                documento=codigo,
                titulo_documento=titulo_documento,
                version=version,
                seccion=seccion_actual,
                titulo_seccion=titulo_actual,
                texto=cuerpo,
                titulo_padre=titulo_padre,
            )
        )

    for linea in texto.splitlines():
        # La subsección se comprueba primero: aunque los patrones no se
        # solapan hoy —«3.1.» no casa con `\d+\.\s+` porque tras el punto no
        # hay espacio—, depender de eso es frágil.
        sub = _SUBSECCION.match(linea)
        sec = _SECCION.match(linea) if sub is None else None

        if sec:
            cerrar()
            seccion_actual = sec.group(1)
            titulo_actual = sec.group(2).strip()
            # El título de una sección pasa a ser el contexto de las
            # subsecciones que vengan detrás.
            titulo_padre = ""
            acumulado = []
        elif sub:
            padre_de_esta = titulo_actual if "." not in (seccion_actual or ".") else titulo_padre
            cerrar()
            seccion_actual = sub.group(1)
            titulo_padre = padre_de_esta
            # Una subsección no tiene título propio: su primera frase ES el
            # contenido. Hereda como título el de su sección.
            titulo_actual = ""
            acumulado = [sub.group(2).strip()]
        elif seccion_actual is not None:
            acumulado.append(linea)

    cerrar()
    return fragmentos


def ingerir(carpeta: Path) -> tuple[list[Fragmento], ReporteDeIngesta]:
    """Lee todos los PDF de una carpeta y devuelve sus fragmentos y el reporte.

    Un documento ilegible se registra y no detiene a los demás: quedarse sin
    cuatro políticas porque una falló sería peor que responder con cuatro y
    declarar que falta una.

    Ante una carpeta sin PDF devuelve lista vacía y un reporte en cero. Que no
    haya documentos es un resultado válido —y visible en el reporte—, no un
    error.
    """
    fragmentos: list[Fragmento] = []
    ilegibles: list[str] = []
    descartados = 0
    leidos = 0

    for ruta in sorted(carpeta.glob("*.pdf")):
        try:
            texto = extraer_texto(ruta)
        except ErrorDeIngesta as error:
            logger.warning("documento_ilegible", extra={"documento": ruta.name})
            ilegibles.append(f"{ruta.name}: {error}")
            continue

        leidos += 1
        codigo, titulo, version = leer_cabecera(texto, respaldo=ruta.stem)
        for fragmento in fragmentar(texto, codigo, titulo, version):
            if len(fragmento.texto) < LARGO_MINIMO_FRAGMENTO:
                descartados += 1
                continue
            fragmentos.append(fragmento)

    reporte = ReporteDeIngesta(
        documentos_leidos=leidos,
        fragmentos=len(fragmentos),
        descartados_por_cortos=descartados,
        documentos_ilegibles=ilegibles,
    )
    logger.info(
        "ingesta_terminada",
        extra={
            "documentos": leidos,
            "fragmentos": len(fragmentos),
            "descartados": descartados,
            "ilegibles": len(ilegibles),
        },
    )
    return fragmentos, reporte

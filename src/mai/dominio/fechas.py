"""Normalización de las fechas del histórico de tickets.

El histórico trae tres formatos repartidos casi en tercios (medido sobre los
2.000 registros: ISO 676, dd/mm/aaaa 663, dd-Mmm-aaaa 661). El tercero usa
meses abreviados **en español**.

Por qué el mapa de meses es explícito y no `%b`:
    `datetime.strptime` con `%b` resuelve el nombre del mes usando el locale
    del proceso. En un servidor con locale C —lo normal en un contenedor y en
    integración continua— "Abr" no existe y la conversión falla. El mismo
    código funcionaría en la máquina del desarrollador y fallaría en
    producción. Un mapa explícito no depende del entorno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# Formatos que `strptime` resuelve sin depender del locale: solo dígitos.
FORMATOS_NUMERICOS = ("%Y-%m-%d", "%d/%m/%Y")

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Se usan para diagnosticar POR QUÉ falló una fecha, no para convertirla.
_FORMA_ISO = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_FORMA_BARRAS = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_FORMA_MES_TEXTO = re.compile(r"^(\d{1,2})-([A-Za-zÁÉÍÓÚáéíóú]{3,})-(\d{4})$")

MOTIVO_FECHA_INEXISTENTE = "fecha_inexistente"
MOTIVO_MES_NO_RECONOCIDO = "mes_no_reconocido"
MOTIVO_FORMATO_NO_RECONOCIDO = "formato_no_reconocido"


@dataclass(frozen=True)
class FechaNormalizada:
    """Resultado de normalizar una fecha. Distingue tres estados.

    - Válida:   `valor` tiene la fecha, `motivo_rechazo` es None.
    - Vacía:    ambos None. El campo venía sin dato y eso puede ser legítimo
                (1.299 `fecha_cierre` del histórico son tickets abiertos).
    - Rechazada: `valor` es None y `motivo_rechazo` dice por qué. Ese motivo
                es el que acompaña al registro en cuarentena.
    """

    valor: date | None
    motivo_rechazo: str | None

    @property
    def es_valida(self) -> bool:
        return self.valor is not None

    @property
    def esta_vacia(self) -> bool:
        return self.valor is None and self.motivo_rechazo is None

    @property
    def fue_rechazada(self) -> bool:
        return self.motivo_rechazo is not None


def normalizar_fecha(valor: object) -> FechaNormalizada:
    """Convierte una fecha del histórico a `date`.

    Recibe cualquier valor (lo que venga de la columna del CSV).
    Devuelve un `FechaNormalizada` con uno de los tres estados descritos
    arriba. **Nunca lanza excepción y nunca descarta en silencio:** una
    entrada que no se puede convertir vuelve con el motivo del rechazo.
    """
    texto = _a_texto_limpio(valor)
    if not texto:
        return FechaNormalizada(valor=None, motivo_rechazo=None)

    for formato in FORMATOS_NUMERICOS:
        try:
            return FechaNormalizada(datetime.strptime(texto, formato).date(), None)
        except ValueError:
            continue

    fecha = _intentar_mes_en_espanol(texto)
    if fecha is not None:
        return FechaNormalizada(valor=fecha, motivo_rechazo=None)

    return FechaNormalizada(valor=None, motivo_rechazo=_diagnosticar(texto))


def _a_texto_limpio(valor: object) -> str:
    """Normaliza el valor crudo a texto. El BOM se cuela como primer carácter
    de la primera celda cuando el CSV se guardó desde Excel."""
    if valor is None:
        return ""
    return str(valor).replace("﻿", "").strip()


def _intentar_mes_en_espanol(texto: str) -> date | None:
    """Resuelve el formato dd-Mmm-aaaa con el mapa explícito de meses."""
    coincidencia = _FORMA_MES_TEXTO.match(texto)
    if coincidencia is None:
        return None

    dia_txt, mes_txt, anio_txt = coincidencia.groups()
    mes = MESES_ES.get(mes_txt[:3].lower())
    if mes is None:
        return None

    try:
        return date(int(anio_txt), mes, int(dia_txt))
    except ValueError:
        # Coincide con la forma pero el día no existe en ese mes: 31-Feb-2025.
        return None


def _diagnosticar(texto: str) -> str:
    """Explica por qué no se pudo convertir.

    Separar «la forma es conocida pero la fecha no existe» de «no reconozco
    esta forma» importa: la primera señala un dato mal capturado y la segunda,
    un formato que el histórico no declaraba. Son dos problemas distintos y el
    reporte de calidad los cuenta por separado.
    """
    if _FORMA_ISO.match(texto) or _FORMA_BARRAS.match(texto):
        return MOTIVO_FECHA_INEXISTENTE

    coincidencia = _FORMA_MES_TEXTO.match(texto)
    if coincidencia is not None:
        mes_txt = coincidencia.group(2)
        if mes_txt[:3].lower() not in MESES_ES:
            return MOTIVO_MES_NO_RECONOCIDO
        return MOTIVO_FECHA_INEXISTENTE

    return MOTIVO_FORMATO_NO_RECONOCIDO

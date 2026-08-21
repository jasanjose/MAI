"""Catálogos cerrados del dominio y normalización de sus valores.

El histórico escribe el mismo valor de muchas formas: mayúsculas, tildes,
sinónimos y un esquema numerado heredado (`1-Alta`, `2-Media`, `3-Baja`).
Medido sobre los 2.000 registros: 58 variantes de categoría, 14 de
prioridad, 11 de estado y 7 de canal.

Este módulo tiene **dos usos, no uno**:

1. Sanear el histórico en la etapa 1.
2. Validar la salida del modelo de lenguaje en la etapa 2. El estándar del
   proyecto (§5.3) exige que ninguna salida de un modelo llegue a la base de
   datos sin contrastarse contra un catálogo cerrado. `CATEGORIAS_VALIDAS`
   es ese catálogo.

Las claves de búsqueda van sin tildes y en minúscula; los valores canónicos
sí las llevan, porque son los que se muestran.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MOTIVO_FUERA_DE_CATALOGO = "valor_fuera_de_catalogo"

# El histórico numera la prioridad: "1-Alta", "2-Media", "3-Baja".
_PREFIJO_NUMERADO = re.compile(r"^\d+\s*-\s*")
_ESPACIOS = re.compile(r"\s+")

# ── Categorías ──────────────────────────────────────────────────────────────
# Las 58 variantes del histórico colapsan en 12 al unir sinónimos, y 12 es
# exactamente lo que declara el catálogo de servicios del requerimiento R-01.
CATALOGO_CATEGORIA: dict[str, str] = {
    "software": "Software",
    "aplicaciones": "Software",
    "accesos": "Accesos",
    "acceso": "Accesos",
    "gestion de accesos": "Accesos",
    "hardware": "Hardware",
    "equipos": "Hardware",
    "red": "Red",
    "conectividad": "Red",
    "incidente": "Incidentes",
    "incidentes": "Incidentes",
    "nomina": "Nómina",
    "compras": "Compras",
    "ordenes de compra": "Compras",
    "informes": "Informes",
    "reportes": "Informes",
    "vacaciones": "Vacaciones",
    "otros": "Otros",
    "viaticos": "Viáticos",
    "capacitacion": "Capacitación",
}

# "Sin clasificar" NO es una decimotercera categoría: es ausencia de
# etiqueta, igual que la celda vacía. Se tratan como el mismo estado.
_AUSENCIA_DE_CATEGORIA = frozenset({"sin clasificar", "sin categoria", "n/a", "-"})

CATALOGO_PRIORIDAD: dict[str, str] = {
    "critica": "Crítica",
    "alta": "Alta",
    "media": "Media",
    "baja": "Baja",
}

CATALOGO_ESTADO: dict[str, str] = {
    "abierto": "Abierto",
    "en proceso": "En proceso",
    "cerrado": "Cerrado",
    "reabierto": "Reabierto",
    "escalado": "Escalado",
}

CATALOGO_CANAL: dict[str, str] = {
    "correo": "Correo",
    "telefono": "Teléfono",
    "formulario": "Formulario",
    "formulario web": "Formulario",
    "mesa de ayuda": "Mesa de ayuda",
}

# Lo que puede devolver el modelo de lenguaje y nada más.
CATEGORIAS_VALIDAS = frozenset(CATALOGO_CATEGORIA.values())
PRIORIDADES_VALIDAS = frozenset(CATALOGO_PRIORIDAD.values())
ESTADOS_VALIDOS = frozenset(CATALOGO_ESTADO.values())
CANALES_VALIDOS = frozenset(CATALOGO_CANAL.values())


@dataclass(frozen=True)
class ValorNormalizado:
    """Mismo contrato de tres estados que `FechaNormalizada`.

    - Válido:   `valor` trae la forma canónica.
    - Vacío:    ambos None. El campo venía sin dato.
    - Rechazado: `valor` es None y `motivo_rechazo` dice por qué.
    """

    valor: str | None
    motivo_rechazo: str | None

    @property
    def es_valido(self) -> bool:
        return self.valor is not None

    @property
    def esta_vacio(self) -> bool:
        return self.valor is None and self.motivo_rechazo is None

    @property
    def fue_rechazado(self) -> bool:
        return self.motivo_rechazo is not None


def clave_de_busqueda(valor: object) -> str:
    """Reduce un valor escrito de cualquier forma a su clave de catálogo.

    Quita tildes, pasa a minúscula, colapsa espacios y elimina el prefijo
    numerado del histórico. Es lo que hace que las 14 variantes de prioridad
    entren en un mapa de 4 líneas en vez de uno de 14.
    """
    if valor is None:
        return ""
    texto = str(valor).replace("﻿", "").strip().lower()
    texto = _PREFIJO_NUMERADO.sub("", texto)
    texto = _ESPACIOS.sub(" ", texto)
    sin_tildes = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").strip()


def _normalizar_contra(catalogo: dict[str, str], valor: object) -> ValorNormalizado:
    clave = clave_de_busqueda(valor)
    if not clave:
        return ValorNormalizado(valor=None, motivo_rechazo=None)

    canonico = catalogo.get(clave)
    if canonico is None:
        return ValorNormalizado(valor=None, motivo_rechazo=MOTIVO_FUERA_DE_CATALOGO)
    return ValorNormalizado(valor=canonico, motivo_rechazo=None)


def normalizar_categoria(valor: object) -> ValorNormalizado:
    """Lleva una categoría a una de las 12 del catálogo de servicios.

    Devuelve el estado «vacío» tanto para la celda vacía como para
    «Sin clasificar»: ambos significan que el ticket no tiene etiqueta, y
    tratarlos distinto inventaría una categoría que no existe.
    """
    if clave_de_busqueda(valor) in _AUSENCIA_DE_CATEGORIA:
        return ValorNormalizado(valor=None, motivo_rechazo=None)
    return _normalizar_contra(CATALOGO_CATEGORIA, valor)


def normalizar_prioridad(valor: object) -> ValorNormalizado:
    """Lleva una prioridad a Crítica, Alta, Media o Baja.

    Las cuatro coinciden con las que define la política de incidentes
    POL-TIC-05 §3, no son una invención de este módulo.
    """
    return _normalizar_contra(CATALOGO_PRIORIDAD, valor)


def normalizar_estado(valor: object) -> ValorNormalizado:
    """Lleva un estado a uno de los cinco del ciclo de vida del ticket."""
    return _normalizar_contra(CATALOGO_ESTADO, valor)


def normalizar_canal(valor: object) -> ValorNormalizado:
    """Lleva un canal a uno de los cuatro por los que entra una solicitud."""
    return _normalizar_contra(CATALOGO_CANAL, valor)

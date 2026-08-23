"""Identificador de traza, propagado extremo a extremo.

Cada petición lleva un `id_traza` que aparece en todos los registros que
genera y en la respuesta de error que recibe el cliente. Sirve para lo único
que importa cuando algo falla en producción: que quien reporta el problema
pueda dar un identificador y quien lo investiga encuentre exactamente esa
petición entre millones de líneas.

Se guarda en un `ContextVar` y no en una variable global ni en un atributo
del objeto petición. Un `ContextVar` es propio de cada tarea asíncrona, así
que dos peticiones concurrentes no se pisan el identificador — con una
variable global, bajo carga, los registros de una petición aparecerían con el
identificador de otra, que es peor que no tener identificador: manda a
investigar al sitio equivocado.

El identificador se acepta si el cliente lo envía en `X-Id-Traza`. Eso permite
seguir una operación que atraviesa varios servicios con un solo valor. Si no
viene, se genera.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

CABECERA_TRAZA = "X-Id-Traza"

# Largo máximo aceptado de un identificador ajeno. Sin cota, un cliente puede
# meter kilobytes en cada línea de registro.
LARGO_MAXIMO = 64

_id_traza: ContextVar[str] = ContextVar("id_traza", default="")


def generar_id_traza() -> str:
    """Identificador nuevo, único y sin significado propio."""
    return uuid.uuid4().hex


def normalizar_id_traza(valor: str | None) -> str:
    """Acepta el identificador del cliente si es utilizable, o genera uno.

    Se rechaza y se reemplaza cuando viene vacío, cuando excede el largo
    máximo o cuando trae caracteres que no son alfanuméricos, guion o guion
    bajo. Ese último filtro no es estética: el identificador se escribe en los
    registros, y un valor con saltos de línea permitiría a un cliente
    fabricar entradas de registro falsas.
    """
    if not valor:
        return generar_id_traza()
    limpio = valor.strip()
    if not limpio or len(limpio) > LARGO_MAXIMO:
        return generar_id_traza()
    if not all(c.isalnum() or c in "-_" for c in limpio):
        return generar_id_traza()
    return limpio


def fijar_id_traza(valor: str) -> None:
    """Fija el identificador de la petición en curso."""
    _id_traza.set(valor)


def id_traza_actual() -> str:
    """El identificador de la petición en curso, o cadena vacía fuera de una."""
    return _id_traza.get()

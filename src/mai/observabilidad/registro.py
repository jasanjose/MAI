"""Registro estructurado en JSON.

Una línea de registro por evento, en JSON, para que se pueda consultar con
herramientas en vez de leerla a ojo. `print` no aparece en ninguna parte del
sistema: no lleva nivel, no lleva marca de tiempo, no se puede filtrar y no
se puede apagar.

**Los registros no llevan datos personales ni contenido de tickets**
(estándar §7). Llevan identificadores y medidas: el código de la solicitud,
el área, la categoría, la latencia. Nunca el asunto, la descripción ni el
correo del solicitante. Un sistema de registro es una copia de los datos con
menos controles de acceso que la base de datos, y suele conservarse más
tiempo.

Cada evento arrastra el `id_traza` de la petición en curso sin que quien
registra tenga que acordarse de pasarlo. Que dependa de la memoria de quien
escribe el código es garantizar que falte justo en el evento que importa.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from mai.observabilidad.traza import id_traza_actual

VARIABLE_NIVEL = "MAI_NIVEL_LOG"
NIVEL_POR_DEFECTO = "INFO"

# Atributos que `logging` pone en todo registro. Se excluyen para quedarse
# solo con los campos que el llamador pasó en `extra`, que son los que
# describen el evento.
_ATRIBUTOS_ESTANDAR = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "stacklevel", "taskName", "thread",
        "threadName",
    }
)

# Nombres que nunca deben salir en un registro, aunque alguien los pase por
# descuido. La lista es corta a propósito: es una red de seguridad, no el
# mecanismo principal. El mecanismo principal es no pasarlos.
CAMPOS_PROHIBIDOS = frozenset({"asunto", "descripcion", "solicitante", "correo", "texto"})

MARCA_OMITIDO = "«omitido: dato personal o contenido»"


class FormateadorJSON(logging.Formatter):
    """Convierte un registro de `logging` en una línea JSON."""

    def format(self, registro: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "momento": self.formatTime(registro, "%Y-%m-%dT%H:%M:%S%z"),
            "nivel": registro.levelname,
            "evento": registro.getMessage(),
            "modulo": registro.name,
        }

        traza = id_traza_actual()
        if traza:
            evento["id_traza"] = traza

        for clave, valor in registro.__dict__.items():
            if clave in _ATRIBUTOS_ESTANDAR or clave.startswith("_"):
                continue
            evento[clave] = MARCA_OMITIDO if clave in CAMPOS_PROHIBIDOS else valor

        if registro.exc_info:
            # El tipo y el mensaje de la excepción, no la traza completa: la
            # traza puede arrastrar valores de variables locales.
            tipo, error, _ = registro.exc_info
            evento["excepcion"] = {
                "tipo": tipo.__name__ if tipo else None,
                "mensaje": str(error) if error else None,
            }

        # `default=str` para que una fecha o un objeto sin serializar no
        # tumben el registro. Perder una línea por un tipo raro sería cambiar
        # un problema de formato por uno de ceguera.
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_registro(nivel: str | None = None, salida=None) -> None:
    """Deja el registro raíz emitiendo JSON por la salida indicada.

    Es idempotente: llamarla dos veces no duplica los manejadores. Sin esa
    guarda, dos llamadas producirían cada línea dos veces, que es un defecto
    difícil de rastrear porque el contenido es correcto.
    """
    nivel = nivel or os.environ.get(VARIABLE_NIVEL, NIVEL_POR_DEFECTO)
    raiz = logging.getLogger()

    for manejador in list(raiz.handlers):
        raiz.removeHandler(manejador)

    manejador = logging.StreamHandler(salida or sys.stdout)
    manejador.setFormatter(FormateadorJSON())
    raiz.addHandler(manejador)
    raiz.setLevel(nivel.upper())

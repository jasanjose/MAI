"""Construcción de la cadena de proveedores a partir del entorno.

Este es el único sitio del sistema que sabe **qué proveedores existen**. El
dominio conoce el puerto; los adaptadores conocen un protocolo; aquí se
decide quién entra en la cadena y en qué orden, leyendo variables de entorno.

Es la pieza que hace literal el criterio de aceptación de `CLAUDE.md` §3:
*«cambiar de proveedor debe ser cambiar la variable de entorno. Cero líneas
de código.»*

    RUTA_CLASIFICACION=groq,dashscope
    RUTA_RAG=openai,dashscope
    RUTA_CLASIFICACION=falso            # en CI: sin red, sin credenciales

Un proveedor mal configurado **falla al construir la cadena, no en la primera
petición de un usuario**. Y la cadena no se acorta en silencio: si se pidió
`groq,dashscope` y falta la credencial de la segunda, se lanza un error en vez
de arrancar con un solo eslabón. Una cadena que uno cree con reserva y no la
tiene es peor que una sin reserva, porque el descubrimiento ocurre durante el
incidente.

El entorno se recibe por parámetro y no se lee de `os.environ` directamente.
Así las pruebas construyen cadenas sin tocar el proceso, y el punto donde se
leen las credenciales queda en un solo lugar visible.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from mai.adaptadores.llm.compatible import AdaptadorCompatible
from mai.adaptadores.llm.enrutador import EnrutadorLLM
from mai.adaptadores.llm.falso import AdaptadorFalso
from mai.dominio.puertos import ProveedorLLM

NOMBRE_FALSO = "falso"

# Los proveedores que hablan Chat Completions y sus prefijos de variable.
# Añadir uno nuevo es añadir una línea aquí y tres variables al entorno.
PROVEEDORES_COMPATIBLES: dict[str, str] = {
    "groq": "GROQ",
    "dashscope": "DASHSCOPE",
    "openai": "OPENAI",
    "openrouter": "OPENROUTER",
    "ollama": "OLLAMA",
}

VARIABLE_RUTA_CLASIFICACION = "RUTA_CLASIFICACION"
VARIABLE_RUTA_RAG = "RUTA_RAG"

RUTA_POR_DEFECTO = NOMBRE_FALSO


class ConfiguracionInvalida(Exception):
    """La configuración del entorno no permite construir la cadena pedida."""


def construir_cadena(
    ruta: str,
    entorno: Mapping[str, str] | None = None,
    nombre: str = "cadena",
) -> ProveedorLLM:
    """Arma la cadena descrita por `ruta`, una lista de nombres por comas.

    Devuelve siempre un `ProveedorLLM`. Con un solo nombre también devuelve
    un enrutador de un eslabón, para que el resto del sistema no tenga dos
    formas distintas de recibir un proveedor.

    Lanza `ConfiguracionInvalida` si la ruta está vacía, nombra un proveedor
    desconocido, o falta alguna variable de un proveedor nombrado.
    """
    entorno = os.environ if entorno is None else entorno

    nombres = [n.strip().lower() for n in ruta.split(",") if n.strip()]
    if not nombres:
        raise ConfiguracionInvalida(
            "La ruta de proveedores está vacía. Indique al menos uno, "
            f"por ejemplo «{NOMBRE_FALSO}» para correr sin red."
        )

    return EnrutadorLLM([_construir_uno(n, entorno) for n in nombres], nombre=nombre)


def construir_para_clasificacion(entorno: Mapping[str, str] | None = None) -> ProveedorLLM:
    """Cadena de la tarea de clasificar. Manda la latencia y el costo (R-01)."""
    entorno = os.environ if entorno is None else entorno
    ruta = entorno.get(VARIABLE_RUTA_CLASIFICACION, RUTA_POR_DEFECTO)
    return construir_cadena(ruta, entorno, nombre="clasificacion")


def construir_para_rag(entorno: Mapping[str, str] | None = None) -> ProveedorLLM:
    """Cadena de la tarea de responder políticas. Manda la fidelidad (R-02)."""
    entorno = os.environ if entorno is None else entorno
    ruta = entorno.get(VARIABLE_RUTA_RAG, RUTA_POR_DEFECTO)
    return construir_cadena(ruta, entorno, nombre="rag")


# ── Interno ─────────────────────────────────────────────────────────────────


def _construir_uno(nombre: str, entorno: Mapping[str, str]) -> ProveedorLLM:
    if nombre == NOMBRE_FALSO:
        return AdaptadorFalso(nombre=NOMBRE_FALSO)

    prefijo = PROVEEDORES_COMPATIBLES.get(nombre)
    if prefijo is None:
        conocidos = ", ".join(sorted([*PROVEEDORES_COMPATIBLES, NOMBRE_FALSO]))
        raise ConfiguracionInvalida(
            f"Proveedor desconocido: «{nombre}». Los disponibles son: {conocidos}."
        )

    valores = {
        sufijo: (entorno.get(f"{prefijo}_{sufijo}") or "").strip()
        for sufijo in ("BASE_URL", "API_KEY", "MODEL")
    }
    faltantes = [f"{prefijo}_{s}" for s, v in valores.items() if not v]
    if faltantes:
        # El mensaje nombra las variables que faltan, nunca sus valores.
        raise ConfiguracionInvalida(
            f"Al proveedor «{nombre}» le faltan variables de entorno: "
            f"{', '.join(faltantes)}. Si no va a usarlo, quítelo de la ruta."
        )

    return AdaptadorCompatible(
        nombre=nombre,
        base_url=valores["BASE_URL"],
        api_key=valores["API_KEY"],
        modelo=valores["MODEL"],
    )

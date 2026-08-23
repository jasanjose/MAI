"""Punto de entrada de la aplicación.

    uvicorn mai.api.main:app --port 8000
    python -m mai.api                      (equivalente, con recarga apagada)

Aquí —y solo aquí— se configura el registro global. `crear_app` no lo hace a
propósito: una fábrica que toca el registro raíz cambia el comportamiento de
cualquier prueba que la use, y esos efectos aparecen lejos de donde se
originaron. La configuración global pertenece al punto de entrada, que es el
único sitio donde «global» significa algo.
"""

from __future__ import annotations

import os

from mai.api.app import crear_app
from mai.observabilidad.registro import configurar_registro

PUERTO_POR_DEFECTO = 8000

configurar_registro()

app = crear_app()


def main() -> None:
    """Levanta el servidor. `uvicorn` se importa aquí y no arriba porque
    solo hace falta al ejecutar, no al importar la aplicación."""
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("MAI_HOST", "127.0.0.1"),
        port=int(os.environ.get("MAI_PUERTO", PUERTO_POR_DEFECTO)),
        log_config=None,  # que no reemplace el formateador JSON con el suyo
    )


if __name__ == "__main__":
    main()

"""Script de saneamiento del histórico de tickets.

    python -m mai.limpiar_historico ENTRADA.csv [--salida DIRECTORIO]

Produce tres archivos y un reporte de calidad por consola:

    tickets_limpios.csv   los registros que superaron validación
    cuarentena.csv        los apartados, con su motivo y su fila original
    resumen.csv           totales por área y por prioridad

El código de salida es 0 si el proceso terminó, 1 si no pudo leer la
entrada, y 2 si la tasa de cuarentena supera el umbral aceptable — así el
proceso sirve dentro de una tubería automatizada y no solo a mano.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from mai.adaptadores.persistencia.csv_tickets import (
    escribir_cuarentena,
    escribir_resumen,
    escribir_tickets,
    leer_tickets,
)
from mai.dominio.limpieza import limpiar_tickets
from mai.dominio.resumen import resumir

# Por encima de esto el problema no son los registros: es la fuente.
UMBRAL_CUARENTENA_PCT = 10.0

CODIGO_OK = 0
CODIGO_ENTRADA_ILEGIBLE = 1
CODIGO_CALIDAD_INSUFICIENTE = 2

logger = logging.getLogger("mai.limpieza")


def construir_argumentos(argumentos: list[str] | None = None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m mai.limpiar_historico",
        description="Sanea el histórico de tickets y produce un reporte de calidad.",
    )
    analizador.add_argument("entrada", type=Path, help="CSV del histórico de tickets")
    analizador.add_argument(
        "--salida", type=Path, default=Path("salida"),
        help="directorio donde escribir los resultados (por defecto: salida/)",
    )
    analizador.add_argument(
        "--umbral-cuarentena", type=float, default=UMBRAL_CUARENTENA_PCT,
        help="porcentaje de cuarentena a partir del cual el proceso falla",
    )
    return analizador.parse_args(argumentos)


def main(argumentos: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    opciones = construir_argumentos(argumentos)

    try:
        filas = leer_tickets(opciones.entrada)
    except FileNotFoundError as error:
        # Mensaje para una persona, no una traza.
        print(f"Error: {error}", file=sys.stderr)
        return CODIGO_ENTRADA_ILEGIBLE
    except UnicodeDecodeError:
        print(
            f"Error: no se pudo leer «{opciones.entrada}» como texto UTF-8. "
            "Verifique que sea un CSV y no un archivo binario.",
            file=sys.stderr,
        )
        return CODIGO_ENTRADA_ILEGIBLE

    resultado = limpiar_tickets(filas)
    resumen = resumir(resultado.tickets)

    escribir_tickets(opciones.salida / "tickets_limpios.csv", resultado.tickets)
    escribir_cuarentena(opciones.salida / "cuarentena.csv", resultado.cuarentena)
    escribir_resumen(opciones.salida / "resumen.csv", resumen)

    print(resultado.reporte.como_texto())
    print()
    print(resumen.como_texto())
    print(f"\nArchivos escritos en: {opciones.salida.resolve()}")

    if not filas:
        # Un archivo vacío no es un fallo: es un archivo vacío. Se informa y ya.
        print("\nAviso: la entrada no tenía registros.")
        return CODIGO_OK

    porcentaje = resultado.reporte.en_cuarentena / resultado.reporte.leidos * 100
    if porcentaje > opciones.umbral_cuarentena:
        print(
            f"\nCalidad insuficiente: {porcentaje:.1f} % de los registros quedó en "
            f"cuarentena, por encima del umbral de {opciones.umbral_cuarentena:.1f} %. "
            "Revise la fuente antes de usar esta salida.",
            file=sys.stderr,
        )
        return CODIGO_CALIDAD_INSUFICIENTE

    return CODIGO_OK


if __name__ == "__main__":
    raise SystemExit(main())

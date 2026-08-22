"""Lectura y escritura de archivos CSV.

Todo pasa por el módulo `csv` de la biblioteca estándar, nunca por
concatenación de cadenas. Construir un CSV pegando comas es el defecto que
aparece en el código a revisar de la etapa 5: basta con que un asunto
contenga una coma —«No enciende, urgente»— para que la fila se parta y todas
las columnas siguientes queden corridas, en silencio.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from mai.dominio.limpieza import RegistroEnCuarentena, TicketLimpio
from mai.dominio.resumen import Resumen

COLUMNAS_LIMPIAS = (
    "id", "fecha_creacion", "fecha_cierre", "area", "categoria", "prioridad",
    "canal", "solicitante", "asunto", "descripcion", "estado", "reaperturas",
)
COLUMNAS_CUARENTENA = ("numero_de_fila", "motivo", "detalle", "fila_original")


def leer_tickets(ruta: Path) -> list[dict[str, str]]:
    """Lee el CSV crudo y devuelve las filas como diccionarios.

    `utf-8-sig` descarta la marca de orden de bytes que Excel antepone al
    guardar; sin eso, la primera columna se llamaría «﻿id» y ninguna
    búsqueda por nombre la encontraría.

    Ante un archivo vacío o con solo encabezado devuelve una lista vacía.
    """
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {ruta}")
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def escribir_tickets(ruta: Path, tickets: Iterable[TicketLimpio]) -> int:
    """Escribe los tickets saneados. Devuelve cuántos escribió."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritos = 0
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_LIMPIAS)
        escritor.writeheader()
        for ticket in tickets:
            escritor.writerow(
                {
                    "id": ticket.id,
                    "fecha_creacion": ticket.fecha_creacion.isoformat(),
                    "fecha_cierre": ticket.fecha_cierre.isoformat() if ticket.fecha_cierre else "",
                    "area": ticket.area,
                    "categoria": ticket.categoria,
                    "prioridad": ticket.prioridad,
                    "canal": ticket.canal,
                    "solicitante": ticket.solicitante,
                    "asunto": ticket.asunto,
                    "descripcion": ticket.descripcion,
                    "estado": ticket.estado,
                    "reaperturas": ticket.reaperturas,
                }
            )
            escritos += 1
    return escritos


def escribir_cuarentena(ruta: Path, registros: Iterable[RegistroEnCuarentena]) -> int:
    """Escribe los registros apartados, con su motivo y su fila original.

    La fila original va completa porque la cuarentena no es un contador: es
    material para que alguien corrija el dato en origen.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    escritos = 0
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS_CUARENTENA)
        escritor.writeheader()
        for registro in registros:
            escritor.writerow(
                {
                    "numero_de_fila": registro.numero_de_fila,
                    "motivo": registro.motivo,
                    "detalle": registro.detalle,
                    "fila_original": registro.fila_original,
                }
            )
            escritos += 1
    return escritos


def escribir_resumen(ruta: Path, resumen: Resumen) -> None:
    """Escribe el resumen por área y por prioridad en un solo CSV."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            ["agrupacion", "nombre", "total", "abiertos", "cerrados", "tasa_reapertura_pct"]
        )
        for etiqueta, filas in (("area", resumen.por_area), ("prioridad", resumen.por_prioridad)):
            for fila in filas:
                escritor.writerow(
                    [etiqueta, fila.nombre, fila.total, fila.abiertos,
                     fila.cerrados, fila.tasa_reapertura]
                )

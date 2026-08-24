"""Construcción del índice de políticas desde el entorno.

El corpus no se versiona —no es material propio— así que la ruta se
configura. Si no está configurada, o la carpeta no existe, **el índice se
construye vacío en vez de fallar al arrancar**.

Esa decisión merece explicación, porque lo contrario también es defendible.
Arrancar sin corpus deja el sistema respondiendo consultas de solicitudes con
normalidad y abstiéndose en las de políticas, que es exactamente lo que debe
hacer cuando no tiene evidencia. Fallar al arrancar tumbaría también la parte
que sí funciona.

El riesgo de esa elección es que un despliegue mal configurado se abstenga de
todo en silencio y parezca que el sistema «no sabe nada». Se mitiga
exponiendo el número de fragmentos indexados en `/salud`: cero fragmentos es
visible de un vistazo y diagnostica el problema sin leer registros.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mai.dominio.politicas import RecuperadorDeFragmentos
from mai.rag.indice import IndiceEnMemoria
from mai.rag.ingesta import ingerir
from mai.rag.vectorizacion import VectorizadorTFIDF

logger = logging.getLogger(__name__)

VARIABLE_RUTA = "MAI_RUTA_POLITICAS"


def construir_recuperador(ruta: str | None = None) -> RecuperadorDeFragmentos:
    """Índice de políticas listo para consultar.

    Con `ruta` en None se lee `MAI_RUTA_POLITICAS`. Si la carpeta no existe o
    no tiene PDF, devuelve un índice vacío y lo registra: el sistema arranca y
    se abstiene, en vez de no arrancar.
    """
    valor = ruta if ruta is not None else os.environ.get(VARIABLE_RUTA, "")
    carpeta = Path(valor) if valor else None

    if carpeta is None or not carpeta.is_dir():
        logger.warning(
            "corpus_de_politicas_no_encontrado",
            extra={"variable": VARIABLE_RUTA, "ruta": str(carpeta) if carpeta else None},
        )
        return IndiceEnMemoria([], VectorizadorTFIDF())

    fragmentos, reporte = ingerir(carpeta)
    if reporte.documentos_ilegibles:
        logger.warning(
            "documentos_de_politicas_ilegibles",
            extra={"cuantos": len(reporte.documentos_ilegibles)},
        )
    return IndiceEnMemoria(fragmentos, VectorizadorTFIDF())

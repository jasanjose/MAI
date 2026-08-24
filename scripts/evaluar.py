"""Ejecuta la suite de evaluación y termina con código distinto de cero si falla.

    python scripts/evaluar.py [carpeta_de_politicas]

Pensado para correr en integración continua. **Termina en 1 si algún umbral
no se cumple**, que es lo que convierte la evaluación en una barrera y no en
un informe que nadie lee.

Sin carpeta de políticas no falla: informa que no hay corpus y termina en 0.
Que la evaluación no pueda correr no es lo mismo que que el sistema falle, y
confundirlos haría que un despliegue sin corpus se viera igual que uno roto.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mai.adaptadores.llm.fabrica import VARIABLE_RUTA_RAG, construir_para_rag
from mai.dominio.politicas import ServicioDePoliticas
from mai.evaluacion.suite import cargar_referencia, evaluar, verificar_umbrales
from mai.rag.fabrica import construir_recuperador

RAIZ = Path(__file__).resolve().parent.parent
REFERENCIA = RAIZ / "docs" / "conjunto_referencia.csv"
CORPUS_POR_DEFECTO = RAIZ / "INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/politicas"


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CORPUS_POR_DEFECTO
    if not carpeta.is_dir():
        print(f"Sin corpus de políticas en {carpeta}: la evaluación no se ejecuta.")
        print("No es un fallo del sistema — es que no hay contra qué evaluarlo.")
        return 0

    ruta_rag = os.environ.get(VARIABLE_RUTA_RAG, "falso")
    proveedor_real = ruta_rag.strip().lower() != "falso"

    recuperador = construir_recuperador(str(carpeta))
    servicio = ServicioDePoliticas(recuperador, construir_para_rag())
    casos = cargar_referencia(REFERENCIA)

    resultado = evaluar(servicio, recuperador, casos, proveedor_real=proveedor_real)

    print(f"proveedor: {ruta_rag}" + ("" if proveedor_real else "  (adaptador de pruebas)"))
    print(f"casos:     {resultado.con_respaldo} con respaldo · "
          f"{resultado.sin_respaldo} sin respaldo\n")
    print(f"  recuperación del fragmento correcto  {resultado.recall:6.0%}   mínimo 90 %")
    print(
        f"  escalamiento por falta de evidencia  {resultado.tasa_escalamiento:6.0%}"
        "   máximo 25 %"
    )
    print(f"  respuestas sin cita verificable      {resultado.respuestas_sin_cita:6}   umbral 0")
    if proveedor_real:
        print(
            f"  abstención sin respaldo              {resultado.tasa_abstencion:6.0%}"
            "   umbral 100 %"
        )
    else:
        print("  abstención sin respaldo              NO MEDIDA con el adaptador de pruebas:")
        print("                                       no cita, así que todo se abstiene por")
        print("                                       la segunda puerta: un 100 % no probaría nada")

    incumplidos = verificar_umbrales(resultado)
    if resultado.fallos:
        print("\nfallos concretos:")
        for fallo in resultado.fallos:
            print(f"  - {fallo}")

    if incumplidos:
        print("\nUMBRALES INCUMPLIDOS:")
        for u in incumplidos:
            print(f"  - {u}")
        return 1

    print("\nTodos los umbrales evaluables se cumplen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Entrena la línea base clásica y mide con dos particiones distintas.

    python scripts/entrenar_clasico.py [ruta_del_csv]

No corre en integración continua: necesita el histórico, que no se versiona.

## Por qué dos particiones y no una

La partición habitual —barajar las filas y separar el 20 %— **da un resultado
falso sobre estos datos**, y el propósito de este script es demostrarlo con
números en vez de advertirlo.

El histórico tiene 2.000 filas y **solo 50 asuntos distintos**: cada texto se
repite unas cuarenta veces. Al barajar por filas, el mismo asunto cae en
entrenamiento y en prueba, y el modelo no generaliza — busca en una tabla que
ya vio.

Partir **por asunto** deja en prueba textos que el modelo nunca vio, que es lo
que una partición debe medir.
"""

from __future__ import annotations

import collections
import csv
import random
import sys
from pathlib import Path

from mai.dominio.catalogos import normalizar_categoria
from mai.evaluacion.clasificador_clasico import (
    NaiveBayes,
    matriz_de_confusion,
    metricas_por_categoria,
)

RAIZ = Path(__file__).resolve().parent.parent
CSV_POR_DEFECTO = (
    RAIZ / "INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/datos/tickets_historicos.csv"
)
SEMILLAS = (42, 7, 13)
PROPORCION_ENTRENAMIENTO = 0.8


def cargar(ruta: Path) -> list[tuple[str, str, str]]:
    """(asunto, texto completo, categoría normalizada) de las filas utilizables."""
    datos = []
    for fila in csv.DictReader(ruta.open(encoding="utf-8")):
        categoria = normalizar_categoria(fila.get("categoria"))
        asunto = (fila.get("asunto") or "").strip()
        texto = f"{asunto} {fila.get('descripcion', '')}".strip()
        if categoria.es_valido and texto:
            datos.append((asunto, texto, categoria.valor))
    return datos


def evaluar(entrena, prueba) -> tuple[float, list[str], list[str]]:
    modelo = NaiveBayes()
    modelo.entrenar([t for t, _ in entrena], [c for _, c in entrena])
    predichas = [modelo.predecir(t).categoria for t, _ in prueba]
    reales = [c for _, c in prueba]
    aciertos = sum(1 for p, r in zip(predichas, reales, strict=True) if p == r)
    return aciertos / len(reales), reales, predichas


def particion_por_fila(datos, semilla):
    """La partición habitual: barajar filas. Sobre estos datos, produce fuga.

    `random` con semilla fija es exactamente lo que hace falta aquí —una
    partición reproducible— y no protege nada. La regla S311 es correcta en
    general y se documenta la excepción en el punto de uso.
    """
    d = list(datos)
    random.Random(semilla).shuffle(d)  # noqa: S311  # nosec B311
    corte = int(len(d) * PROPORCION_ENTRENAMIENTO)
    return [(t, c) for _, t, c in d[:corte]], [(t, c) for _, t, c in d[corte:]]


def particion_por_asunto(datos, semilla):
    """Agrupa por asunto: la prueba trae textos que el modelo nunca vio."""
    asuntos = sorted({a for a, _, _ in datos})
    barajados = list(asuntos)
    random.Random(semilla).shuffle(barajados)  # noqa: S311  # nosec B311
    corte = int(len(barajados) * PROPORCION_ENTRENAMIENTO)
    entrenamiento = set(barajados[:corte])
    return (
        [(t, c) for a, t, c in datos if a in entrenamiento],
        [(t, c) for a, t, c in datos if a not in entrenamiento],
    )


def main() -> int:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV_POR_DEFECTO
    if not ruta.is_file():
        print(f"No existe el histórico: {ruta}", file=sys.stderr)
        return 1

    datos = cargar(ruta)
    asuntos = {a for a, _, _ in datos}
    categorias = sorted({c for _, _, c in datos})
    frecuencias = collections.Counter(c for _, _, c in datos)
    mayoritaria = max(frecuencias.values()) / len(datos)

    print(f"tickets etiquetados : {len(datos)}")
    repeticiones = len(datos) // len(asuntos)
    print(
        f"asuntos distintos   : {len(asuntos)}   "
        f"<- cada texto se repite ~{repeticiones} veces"
    )
    print(f"categorías          : {len(categorias)}")
    print(f"línea base          : {mayoritaria:.1%}  (predecir siempre la más frecuente)\n")

    print("PARTICIÓN POR FILA — el mismo asunto cae en ambos lados")
    for semilla in SEMILLAS:
        exactitud, _, _ = evaluar(*particion_por_fila(datos, semilla))
        print(f"  semilla {semilla:>2}: {exactitud:6.1%}")

    print("\nPARTICIÓN POR ASUNTO — la prueba trae textos nunca vistos")
    for semilla in SEMILLAS:
        exactitud, reales, predichas = evaluar(*particion_por_asunto(datos, semilla))
        marca = "por DEBAJO de la línea base" if exactitud < mayoritaria else ""
        print(f"  semilla {semilla:>2}: {exactitud:6.1%}  {marca}")

    print("\nMATRIZ DE CONFUSIÓN — partición por fila, semilla 42")
    print("(se muestra esta porque la otra deja categorías sin un solo caso)\n")
    _, reales, predichas = evaluar(*particion_por_fila(datos, 42))
    matriz = matriz_de_confusion(reales, predichas, categorias)

    ancho = max(len(c) for c in categorias)
    print(" " * (ancho + 2) + " ".join(f"{c[:4]:>5}" for c in categorias))
    for real in categorias:
        fila = " ".join(
            f"{matriz[real][pred] or '·':>5}" for pred in categorias
        )
        print(f"  {real:<{ancho}} {fila}")

    print("\nPOR CATEGORÍA")
    metricas = metricas_por_categoria(matriz)
    print(f"  {'categoría':<{ancho}}  {'prec':>6} {'exh':>6} {'f1':>6} {'casos':>6}")
    for categoria in categorias:
        m = metricas[categoria]
        print(
            f"  {categoria:<{ancho}}  {m['precision']:6.2f} {m['exhaustividad']:6.2f} "
            f"{m['f1']:6.2f} {m['casos']:6}"
        )

    print("\nLECTURA")
    print("  La diferencia entre las dos particiones no es ruido: es la medida")
    print("  de cuánto de ese 99 % era memorización. Ver docs/comparacion_enfoques.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

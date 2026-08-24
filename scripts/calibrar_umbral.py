"""Calibra el umbral de similitud para la abstención.

    python scripts/calibrar_umbral.py [carpeta_de_politicas]

No corre en integración continua **y no debería**: necesita el corpus real,
que no se versiona. Su salida sí se versiona, en `docs/calibracion_umbral.md`,
para que la elección del umbral quede con los datos que la sustentan y no como
un número aparecido en el código.

## Qué mide y por qué esas dos cosas

El umbral separa «tengo evidencia» de «no la tengo», y equivocarse tiene dos
costos que **no valen lo mismo**:

- **Abstenerse teniendo respuesta** cuesta un escalamiento a una persona.
  Molesto y medible; el objetivo de `docs/metricas.md` §4 es ≤ 25 %.
- **Responder sin tenerla** cuesta una reclamación formal ante Talento Humano
  (R-02). El objetivo del mismo documento es **0**, condición dura.

Por eso la tabla no busca el umbral que maximiza aciertos: busca **el más bajo
que aún abstiene en el 100 % de los casos sin respaldo**. Ese criterio se fijó
antes de tener los datos y es el que se aplica aquí.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from mai.rag.indice import IndiceEnMemoria
from mai.rag.ingesta import ingerir
from mai.rag.vectorizacion import VectorizadorTFIDF

RAIZ = Path(__file__).resolve().parent.parent
REFERENCIA = RAIZ / "docs" / "conjunto_referencia.csv"
CORPUS_POR_DEFECTO = RAIZ / "INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/politicas"

SIN_EVIDENCIA = "SIN EVIDENCIA EN LOS DOCUMENTOS"
FRAGMENTOS = 5
UMBRALES = [round(0.02 * i, 2) for i in range(1, 21)]


def cargar_casos() -> tuple[list[dict], list[dict]]:
    """Separa las consultas con respuesta de los casos de abstención.

    Se ignoran las filas de clasificación: no tienen documento de origen y no
    dicen nada sobre el umbral de recuperación.
    """
    con_respuesta, sin_respaldo = [], []
    for fila in csv.DictReader(REFERENCIA.open(encoding="utf-8")):
        esperado = fila["respuesta_o_categoria_esperada"].strip()
        if esperado == SIN_EVIDENCIA:
            sin_respaldo.append(fila)
        elif fila["documento_fuente"].strip():
            con_respuesta.append(fila)
    return con_respuesta, sin_respaldo


def cita_esperada(fila: dict) -> str:
    """`POL-GTH-01_Vacaciones.pdf` + `3.1` → `POL-GTH-01 §3.1`.

    Algunas filas citan dos secciones («5.1 y 5.2») porque la respuesta
    completa las necesita. Se toma la primera: basta con que el recuperador
    llegue a una para que el modelo tenga de dónde partir.
    """
    codigo = fila["documento_fuente"].split("_")[0]
    seccion = fila["seccion_fuente"].split(" y ")[0].strip()
    return f"{codigo} §{seccion}"


def medir(indice, casos: list[dict]) -> list[dict]:
    filas = []
    for caso in casos:
        coincidencias = indice.buscar(caso["pregunta_o_texto"], FRAGMENTOS)
        citas = [c.fragmento.cita for c in coincidencias]
        esperada = cita_esperada(caso) if caso["documento_fuente"].strip() else ""
        filas.append(
            {
                "id": caso["id_caso"],
                "pregunta": caso["pregunta_o_texto"],
                "esperada": esperada,
                "mejor": coincidencias[0].puntaje if coincidencias else 0.0,
                "recuperada": esperada in citas,
                "posicion": citas.index(esperada) + 1 if esperada in citas else None,
            }
        )
    return filas


def main() -> int:
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else CORPUS_POR_DEFECTO
    if not carpeta.is_dir():
        print(f"No existe la carpeta de políticas: {carpeta}", file=sys.stderr)
        return 1

    fragmentos, reporte = ingerir(carpeta)
    indice = IndiceEnMemoria(fragmentos, VectorizadorTFIDF())
    con_respuesta, sin_respaldo = cargar_casos()

    print(f"corpus:     {reporte.documentos_leidos} documentos · {len(fragmentos)} fragmentos")
    print(f"referencia: {len(con_respuesta)} con respuesta · {len(sin_respaldo)} sin respaldo\n")

    medidos = medir(indice, con_respuesta)
    medidos_sin = medir(indice, sin_respaldo)

    print("── Consultas CON respuesta en el corpus")
    print(f"   {'id':8} {'mejor':>6}  {'pos':>4}  pregunta")
    for f in sorted(medidos, key=lambda x: x["mejor"]):
        pos = f["posicion"] or "—"
        print(f"   {f['id']:8} {f['mejor']:6.3f}  {str(pos):>4}  {f['pregunta'][:62]}")

    print("\n── Casos SIN respaldo (debe abstenerse en el 100 %)")
    for f in sorted(medidos_sin, key=lambda x: -x["mejor"]):
        print(f"   {f['id']:8} {f['mejor']:6.3f}        {f['pregunta'][:62]}")

    recuperados = sum(1 for f in medidos if f["recuperada"])
    print(f"\nrecall@{FRAGMENTOS} = {recuperados}/{len(medidos)} "
          f"({recuperados / len(medidos):.0%}) — techo de lo que el umbral puede lograr\n")

    print("── Barrido de umbrales")
    cabecera = (
        f"   {'umbral':>6}  {'responde':>9}  {'abstiene mal':>13}  "
        f"{'abstiene bien':>14}  {'≤25%':>5}  {'100%':>5}"
    )
    print(cabecera)
    for umbral in UMBRALES:
        responde = [f for f in medidos if f["mejor"] >= umbral]
        # Solo cuenta como buena la respuesta cuya evidencia SÍ se recuperó:
        # pasar el umbral con el fragmento equivocado no es responder bien.
        buenas = sum(1 for f in responde if f["recuperada"])
        mal_abstenidas = len(medidos) - len(responde)
        bien_abstenidas = sum(1 for f in medidos_sin if f["mejor"] < umbral)

        tasa_escalamiento = mal_abstenidas / len(medidos)
        abstencion_completa = bien_abstenidas == len(medidos_sin)
        print(
            f"   {umbral:6.2f}  {buenas:4}/{len(medidos):<4}  "
            f"{mal_abstenidas:6}/{len(medidos):<6}  "
            f"{bien_abstenidas:7}/{len(medidos_sin):<6}  "
            f"{'sí' if tasa_escalamiento <= 0.25 else 'NO':>5}  "
            f"{'sí' if abstencion_completa else 'NO':>5}"
        )

    validos = [
        u
        for u in UMBRALES
        if all(f["mejor"] < u for f in medidos_sin)
    ]
    print()
    if validos:
        elegido = min(validos)
        responde = [f for f in medidos if f["mejor"] >= elegido]
        escalamiento = (len(medidos) - len(responde)) / len(medidos)
        print(f"El más bajo que abstiene en el 100 % de los casos sin respaldo: {elegido:.2f}")
        print(f"A ese umbral la tasa de escalamiento es {escalamiento:.0%} "
              f"(objetivo ≤ 25 %): {'cumple' if escalamiento <= 0.25 else 'NO CUMPLE'}")
    else:
        print("NINGÚN umbral del barrido abstiene en el 100 % de los casos sin respaldo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Suite de evaluación del componente de IA.

Mide el sistema contra el conjunto de referencia etiquetado a mano y **falla
si algún umbral de `docs/metricas.md` no se cumple**. Que falle es el punto:
una evaluación que solo informa se lee la primera semana y se ignora después.

## Qué mide, y por qué esas cuatro cosas

| Métrica | Umbral | Naturaleza |
|---|---|---|
| Abstención ante consultas sin respaldo | **100 %** | Condición dura |
| Respuestas emitidas sin cita verificable | **0** | Condición dura |
| Recuperación del fragmento correcto entre los `k` | ≥ 90 % | Objetivo |
| Escalamiento por no encontrar evidencia | ≤ 25 % | Objetivo |

Las dos primeras no admiten umbral parcial. Una abstención del 95 % significa
que uno de cada veinte usuarios recibe una respuesta inventada sobre montos o
plazos **sin forma de distinguirla de una correcta**, y R-02 dice que eso
genera una reclamación formal. No es una métrica que se optimiza: se cumple o
el componente no sirve.

Las dos últimas sí son objetivos: fallan la evaluación pero describen calidad,
no corrección.

## Por qué corre sin credenciales y qué mide entonces

Sin proveedor configurado, el sistema usa el adaptador falso. Ese adaptador
**no cita**, así que la verificación de cita descarta toda respuesta y el
sistema se abstiene siempre. En ese modo la suite mide lo que sí depende del
código propio —recuperación y primera puerta de abstención— y **declara que
la segunda puerta no se midió**, en vez de dar por buena una abstención del
100 % que viene de que el proveedor no responde nada útil.

Con un proveedor real, mide las cuatro.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from mai.dominio.politicas import (
    MOTIVO_SIN_EVIDENCIA,
    ORIGEN_ABSTENCION,
    RecuperadorDeFragmentos,
    ServicioDePoliticas,
)

SIN_EVIDENCIA = "SIN EVIDENCIA EN LOS DOCUMENTOS"

RECALL_MINIMO = 0.90
ESCALAMIENTO_MAXIMO = 0.25
FRAGMENTOS_RECUPERADOS = 5


@dataclass(frozen=True)
class CasoDeReferencia:
    """Una fila del conjunto de referencia."""

    id_caso: str
    pregunta: str
    esperado: str
    cita_esperada: str | None

    @property
    def sin_respaldo(self) -> bool:
        return self.esperado.strip() == SIN_EVIDENCIA


@dataclass
class Resultado:
    """Lo medido, con el detalle para poder investigar cada fallo."""

    con_respaldo: int = 0
    sin_respaldo: int = 0
    recuperados: int = 0
    abstenciones_correctas: int = 0
    respuestas_sin_cita: int = 0
    escalamientos: int = 0
    fallos: list[str] = field(default_factory=list)
    detalle: list[dict] = field(default_factory=list)
    proveedor_real: bool = False

    @property
    def recall(self) -> float:
        return self.recuperados / self.con_respaldo if self.con_respaldo else 0.0

    @property
    def tasa_abstencion(self) -> float:
        return self.abstenciones_correctas / self.sin_respaldo if self.sin_respaldo else 0.0

    @property
    def tasa_escalamiento(self) -> float:
        return self.escalamientos / self.con_respaldo if self.con_respaldo else 0.0


def cargar_referencia(ruta: Path) -> list[CasoDeReferencia]:
    """Lee el conjunto de referencia y descarta las filas de clasificación.

    Una fila sin documento de origen y que no sea un caso de abstención es de
    clasificación: no dice nada sobre este componente.
    """
    casos: list[CasoDeReferencia] = []
    for fila in csv.DictReader(ruta.open(encoding="utf-8")):
        esperado = fila["respuesta_o_categoria_esperada"].strip()
        documento = fila["documento_fuente"].strip()
        if esperado != SIN_EVIDENCIA and not documento:
            continue
        cita = None
        if documento:
            codigo = documento.split("_")[0]
            # Algunas filas citan dos secciones porque la respuesta completa
            # las necesita. Se toma la primera: basta con que el recuperador
            # llegue a una para que el modelo tenga de dónde partir.
            seccion = fila["seccion_fuente"].split(" y ")[0].strip()
            cita = f"{codigo} §{seccion}"
        casos.append(
            CasoDeReferencia(fila["id_caso"], fila["pregunta_o_texto"], esperado, cita)
        )
    return casos


def evaluar(
    servicio: ServicioDePoliticas,
    recuperador: RecuperadorDeFragmentos,
    casos: list[CasoDeReferencia],
    proveedor_real: bool = False,
) -> Resultado:
    """Corre el conjunto de referencia y acumula las métricas."""
    r = Resultado(proveedor_real=proveedor_real)

    for caso in casos:
        respuesta = servicio.consultar(caso.pregunta)
        se_abstuvo = respuesta.origen == ORIGEN_ABSTENCION

        if caso.sin_respaldo:
            r.sin_respaldo += 1
            if se_abstuvo:
                r.abstenciones_correctas += 1
            else:
                r.fallos.append(
                    f"{caso.id_caso}: respondió a una pregunta sin respaldo "
                    f"— citas {list(respuesta.citas)}"
                )
        else:
            r.con_respaldo += 1
            recuperadas = recuperador.buscar(caso.pregunta, FRAGMENTOS_RECUPERADOS)
            citas = [c.fragmento.cita for c in recuperadas]
            if caso.cita_esperada in citas:
                r.recuperados += 1
            # Escalar por no encontrar evidencia es distinto de escalar porque
            # el modelo no citó: lo primero es un problema de recuperación, lo
            # segundo del modelo. Solo lo primero cuenta como escalamiento.
            if se_abstuvo and respuesta.motivo == MOTIVO_SIN_EVIDENCIA:
                r.escalamientos += 1

        if not se_abstuvo and not respuesta.citas:
            r.respuestas_sin_cita += 1
            r.fallos.append(f"{caso.id_caso}: emitió una respuesta sin ninguna cita")

        r.detalle.append(
            {
                "id": caso.id_caso,
                "sin_respaldo": caso.sin_respaldo,
                "origen": respuesta.origen,
                "motivo": respuesta.motivo,
                "puntaje": round(respuesta.mejor_puntaje, 4),
                "citas": list(respuesta.citas),
            }
        )
    return r


def verificar_umbrales(r: Resultado) -> list[str]:
    """Los umbrales incumplidos. Lista vacía significa que la suite pasa.

    Con proveedor falso, la abstención **no se verifica**: ese adaptador no
    cita, así que todo se abstiene por la segunda puerta y un 100 % ahí no
    demostraría nada. Se declara como no medida en vez de darla por buena.
    """
    incumplidos: list[str] = []

    if r.respuestas_sin_cita > 0:
        incumplidos.append(
            f"CONDICIÓN DURA · {r.respuestas_sin_cita} respuestas sin cita verificable "
            "(el umbral es 0)"
        )

    if r.proveedor_real:
        if r.tasa_abstencion < 1.0:
            incumplidos.append(
                f"CONDICIÓN DURA · abstención {r.tasa_abstencion:.0%} de "
                f"{r.sin_respaldo} casos sin respaldo (el umbral es 100 %)"
            )
    # Sin proveedor real no se evalúa la abstención: ver la docstring.

    if r.recall < RECALL_MINIMO:
        incumplidos.append(
            f"OBJETIVO · recuperación {r.recall:.0%} (el mínimo es {RECALL_MINIMO:.0%})"
        )

    if r.tasa_escalamiento > ESCALAMIENTO_MAXIMO:
        incumplidos.append(
            f"OBJETIVO · escalamiento {r.tasa_escalamiento:.0%} "
            f"(el máximo es {ESCALAMIENTO_MAXIMO:.0%})"
        )

    return incumplidos

"""Pruebas de la suite de evaluación.

La suite es lo que decide si el componente de IA puede salir a producción, así
que ella misma tiene que estar probada: una evaluación que no detecta un fallo
es peor que ninguna, porque da permiso.
"""

from pathlib import Path

import pytest

from mai.dominio.politicas import (
    MOTIVO_SIN_CITA,
    MOTIVO_SIN_EVIDENCIA,
    ORIGEN_ABSTENCION,
    ORIGEN_MODELO,
    RespuestaDePolitica,
)
from mai.evaluacion.suite import (
    ESCALAMIENTO_MAXIMO,
    RECALL_MINIMO,
    CasoDeReferencia,
    Resultado,
    cargar_referencia,
    evaluar,
    verificar_umbrales,
)

REFERENCIA = Path(__file__).parent.parent / "docs" / "conjunto_referencia.csv"


# ── Carga del conjunto de referencia ────────────────────────────────────────


def test_carga_las_consultas_y_los_casos_sin_respaldo():
    casos = cargar_referencia(REFERENCIA)

    assert sum(1 for c in casos if c.sin_respaldo) == 6
    assert sum(1 for c in casos if not c.sin_respaldo) == 21


def test_descarta_las_filas_de_clasificacion():
    """Una fila sin documento de origen que no sea abstención es de
    clasificación: no dice nada sobre este componente."""
    casos = cargar_referencia(REFERENCIA)

    assert all(c.sin_respaldo or c.cita_esperada for c in casos)


def test_construye_la_cita_esperada_desde_el_nombre_y_la_seccion():
    casos = {c.id_caso: c for c in cargar_referencia(REFERENCIA)}

    assert casos["GS-001"].cita_esperada == "POL-GTH-01 §3.1"


def test_toma_la_primera_seccion_cuando_la_fila_cita_dos():
    """«5.1 y 5.2»: basta con que el recuperador llegue a una para que el
    modelo tenga de dónde partir."""
    casos = {c.id_caso: c for c in cargar_referencia(REFERENCIA)}

    assert casos["CO-011"].cita_esperada == "POL-TIC-02 §5.1"


# ── Verificación de umbrales ────────────────────────────────────────────────


def resultado(**cambios) -> Resultado:
    base = {
        "con_respaldo": 20,
        "sin_respaldo": 6,
        "recuperados": 20,
        "abstenciones_correctas": 6,
        "respuestas_sin_cita": 0,
        "escalamientos": 0,
        "proveedor_real": True,
    }
    return Resultado(**{**base, **cambios})


def test_una_evaluacion_perfecta_no_reporta_incumplimientos():
    assert verificar_umbrales(resultado()) == []


def test_una_sola_respuesta_sin_cita_incumple():
    """Condición dura: el umbral es cero, no «pocas»."""
    incumplidos = verificar_umbrales(resultado(respuestas_sin_cita=1))

    assert len(incumplidos) == 1
    assert "CONDICIÓN DURA" in incumplidos[0]


def test_una_sola_abstencion_fallida_incumple():
    """95 % de abstención significa que uno de cada veinte usuarios recibe una
    respuesta inventada sobre montos o plazos."""
    incumplidos = verificar_umbrales(resultado(abstenciones_correctas=5))

    assert any("CONDICIÓN DURA" in i and "abstención" in i for i in incumplidos)


def test_la_abstencion_no_se_evalua_con_el_adaptador_de_pruebas():
    """Ese adaptador no cita, así que todo se abstiene por la segunda puerta y
    un 100 % no demostraría nada. Se declara no medida en vez de darla por
    buena — que es lo que haría verde una suite que no probó nada."""
    peor = resultado(abstenciones_correctas=0, proveedor_real=False)

    assert not any("abstención" in i for i in verificar_umbrales(peor))


def test_una_recuperacion_baja_incumple_como_objetivo():
    incumplidos = verificar_umbrales(resultado(recuperados=10))

    assert any("OBJETIVO" in i and "recuperación" in i for i in incumplidos)


def test_la_recuperacion_justo_en_el_minimo_pasa():
    assert verificar_umbrales(resultado(con_respaldo=10, recuperados=9)) == []
    assert RECALL_MINIMO == 0.90


def test_un_escalamiento_alto_incumple_como_objetivo():
    incumplidos = verificar_umbrales(resultado(escalamientos=10))

    assert any("OBJETIVO" in i and "escalamiento" in i for i in incumplidos)


def test_el_escalamiento_justo_en_el_maximo_pasa():
    assert verificar_umbrales(resultado(con_respaldo=20, escalamientos=5)) == []
    assert ESCALAMIENTO_MAXIMO == 0.25


def test_sin_casos_las_tasas_no_dividen_por_cero():
    vacio = Resultado(proveedor_real=True)

    assert vacio.recall == 0.0
    assert vacio.tasa_abstencion == 0.0
    assert vacio.tasa_escalamiento == 0.0


# ── La evaluación completa, con dobles controlados ──────────────────────────


class ServicioFalso:
    """Responde lo que la prueba le diga, por identificador de caso."""

    def __init__(self, por_pregunta):
        self._por_pregunta = por_pregunta

    def consultar(self, pregunta):
        return self._por_pregunta(pregunta)


class RecuperadorFalso:
    def __init__(self, citas):
        self._citas = citas

    def buscar(self, consulta, cuantos):
        from mai.dominio.politicas import Coincidencia, Fragmento

        return [
            Coincidencia(
                Fragmento("POL-X", "t", "1", cita.split("§")[1], "", "x"), 0.5
            )
            for cita in self._citas
        ]


def respuesta(origen, citas=(), motivo=None):
    return RespuestaDePolitica(
        texto="x", citas=tuple(citas), origen=origen, confianza="alta", motivo=motivo
    )


CASOS = [
    CasoDeReferencia("C1", "¿pregunta con respuesta?", "algo", "POL-X §1"),
    CasoDeReferencia("A1", "¿pregunta sin respaldo?", "SIN EVIDENCIA EN LOS DOCUMENTOS", None),
]


def test_detecta_que_respondio_a_una_pregunta_sin_respaldo():
    """El fallo más grave que la suite existe para atrapar."""
    servicio = ServicioFalso(lambda p: respuesta(ORIGEN_MODELO, ["POL-X §1"]))

    r = evaluar(servicio, RecuperadorFalso(["POL-X §1"]), CASOS, proveedor_real=True)

    assert r.abstenciones_correctas == 0
    assert any("sin respaldo" in f for f in r.fallos)
    assert verificar_umbrales(r)


def test_detecta_una_respuesta_emitida_sin_cita():
    servicio = ServicioFalso(lambda p: respuesta(ORIGEN_MODELO, []))

    r = evaluar(servicio, RecuperadorFalso(["POL-X §1"]), CASOS, proveedor_real=True)

    assert r.respuestas_sin_cita == 2
    assert any("sin ninguna cita" in f for f in r.fallos)


def test_cuenta_como_escalamiento_solo_la_abstencion_por_falta_de_evidencia():
    """Escalar porque no se encontró evidencia es un problema de
    recuperación; escalar porque el modelo no citó es del modelo. Mezclarlos
    haría que mejorar el prompt pareciera empeorar la recuperación."""
    por_falta = ServicioFalso(
        lambda p: respuesta(ORIGEN_ABSTENCION, motivo=MOTIVO_SIN_EVIDENCIA)
    )
    por_no_citar = ServicioFalso(
        lambda p: respuesta(ORIGEN_ABSTENCION, motivo=MOTIVO_SIN_CITA)
    )
    recuperador = RecuperadorFalso(["POL-X §1"])

    assert evaluar(por_falta, recuperador, CASOS, True).escalamientos == 1
    assert evaluar(por_no_citar, recuperador, CASOS, True).escalamientos == 0


def test_el_detalle_permite_investigar_cada_caso():
    servicio = ServicioFalso(lambda p: respuesta(ORIGEN_ABSTENCION, motivo=MOTIVO_SIN_CITA))

    r = evaluar(servicio, RecuperadorFalso([]), CASOS, proveedor_real=True)

    assert [d["id"] for d in r.detalle] == ["C1", "A1"]
    assert all("motivo" in d and "puntaje" in d for d in r.detalle)


# ── Punta a punta contra el sistema real ────────────────────────────────────


@pytest.mark.skipif(
    not (
        Path(__file__).parent.parent
        / "INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/politicas"
    ).is_dir(),
    reason="el corpus de políticas no se versiona; se salta sin él",
)
def test_la_suite_corre_contra_el_sistema_real_y_cumple_los_umbrales_evaluables():
    from mai.adaptadores.llm.falso import AdaptadorFalso
    from mai.dominio.politicas import ServicioDePoliticas
    from mai.rag.fabrica import construir_recuperador

    carpeta = (
        Path(__file__).parent.parent / "INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/politicas"
    )
    recuperador = construir_recuperador(str(carpeta))
    servicio = ServicioDePoliticas(recuperador, AdaptadorFalso())

    r = evaluar(servicio, recuperador, cargar_referencia(REFERENCIA), proveedor_real=False)

    assert r.recall == 1.0
    assert verificar_umbrales(r) == []

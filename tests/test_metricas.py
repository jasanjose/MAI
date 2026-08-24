"""Pruebas de las métricas agregadas."""

import pytest

from mai.observabilidad.metricas import MUESTRAS_MAXIMAS, ColectorDeMetricas, percentil

# ── Percentiles ─────────────────────────────────────────────────────────────


def test_el_percentil_devuelve_un_valor_que_de_verdad_ocurrio():
    """Rango más cercano y no interpolación: un p95 interpolado es un número
    que ninguna petición tardó, y confunde a quien busque la petición lenta."""
    muestras = [10.0, 20.0, 30.0, 40.0]

    assert percentil(muestras, 50) in muestras
    assert percentil(muestras, 95) in muestras


def test_el_percentil_cien_es_el_maximo():
    assert percentil([1.0, 5.0, 100.0], 100) == 100.0


def test_el_percentil_de_una_sola_muestra_es_esa_muestra():
    assert percentil([42.0], 50) == percentil([42.0], 99) == 42.0


def test_el_percentil_de_una_lista_vacia_es_cero_y_no_falla():
    assert percentil([], 95) == 0.0


def test_el_percentil_no_depende_del_orden_de_llegada():
    assert percentil([30.0, 10.0, 20.0], 50) == percentil([10.0, 20.0, 30.0], 50)


# ── Latencias por operación ─────────────────────────────────────────────────


def test_agrupa_las_latencias_por_operacion():
    c = ColectorDeMetricas()

    c.registrar_operacion("POST /solicitudes", 10.0)
    c.registrar_operacion("POST /solicitudes", 20.0)
    c.registrar_operacion("GET /salud", 1.0)

    operaciones = c.resumen()["operaciones"]
    assert operaciones["POST /solicitudes"]["cuenta"] == 2
    assert operaciones["GET /salud"]["cuenta"] == 1


def test_la_memoria_de_latencias_esta_acotada():
    """Guardar todas las latencias de la vida del proceso hace crecer la
    memoria sin techo y desdibuja el presente: un p95 histórico tarda días en
    reflejar que el sistema se degradó hace una hora."""
    c = ColectorDeMetricas()

    for i in range(MUESTRAS_MAXIMAS + 500):
        c.registrar_operacion("POST /solicitudes", float(i))

    assert c.resumen()["operaciones"]["POST /solicitudes"]["cuenta"] == MUESTRAS_MAXIMAS


def test_conserva_las_muestras_mas_recientes_y_no_las_primeras():
    c = ColectorDeMetricas()

    for i in range(MUESTRAS_MAXIMAS + 10):
        c.registrar_operacion("op", float(i))

    # Las diez primeras (0..9) ya salieron; el mínimo debe ser 10.
    assert c.resumen()["operaciones"]["op"]["p50"] > 10


def test_sin_operaciones_el_resumen_no_falla():
    assert ColectorDeMetricas().resumen()["operaciones"] == {}


# ── Tasa de degradación y de abstención ─────────────────────────────────────


def test_calcula_la_tasa_de_degradacion():
    c = ColectorDeMetricas()

    c.registrar_clasificacion("modelo", None)
    c.registrar_clasificacion("modelo", None)
    c.registrar_clasificacion("degradado", "proveedor_no_disponible")
    c.registrar_clasificacion("degradado", "salida_fuera_de_catalogo")

    clasificacion = c.resumen()["clasificacion"]
    assert clasificacion["total"] == 4
    assert clasificacion["degradado"] == 2
    assert clasificacion["tasa_degradado"] == 0.5


def test_desglosa_la_degradacion_por_motivo():
    """Un proveedor caído y un modelo que devuelve basura degradan igual pero
    exigen acciones opuestas. Sin el desglose, la tasa no dice qué hacer."""
    c = ColectorDeMetricas()

    c.registrar_clasificacion("degradado", "proveedor_no_disponible")
    c.registrar_clasificacion("degradado", "proveedor_no_disponible")
    c.registrar_clasificacion("degradado", "salida_fuera_de_catalogo")

    por_motivo = c.resumen()["clasificacion"]["por_motivo"]
    assert por_motivo == {"proveedor_no_disponible": 2, "salida_fuera_de_catalogo": 1}


def test_calcula_la_tasa_de_abstencion():
    c = ColectorDeMetricas()

    c.registrar_consulta("modelo", None)
    c.registrar_consulta("abstencion", "sin_evidencia_suficiente")

    consultas = c.resumen()["consultas"]
    assert consultas["total"] == 2
    assert consultas["tasa_abstencion"] == 0.5


def test_sin_muestras_la_tasa_es_cero_y_no_divide_por_cero():
    resumen = ColectorDeMetricas().resumen()

    assert resumen["clasificacion"]["tasa_degradado"] == 0.0
    assert resumen["consultas"]["tasa_abstencion"] == 0.0


# ── Tokens ──────────────────────────────────────────────────────────────────


def test_acumula_los_tokens_por_llamada():
    c = ColectorDeMetricas()

    c.registrar_llamada_llm("groq", 100, 20)
    c.registrar_llamada_llm("groq", 50, 10)

    llm = c.resumen()["proveedor_llm"]
    assert llm["llamadas"] == 2
    assert llm["tokens_entrada"] == 150
    assert llm["tokens_salida"] == 30


def test_los_tokens_ausentes_se_cuentan_aparte_y_no_como_cero():
    """Sumar ceros haría parecer que el sistema consume menos de lo que
    consume — y esa es justo la métrica que se usa para presupuestar."""
    c = ColectorDeMetricas()

    c.registrar_llamada_llm("falso", None, None)
    c.registrar_llamada_llm("groq", 100, 20)

    llm = c.resumen()["proveedor_llm"]
    assert llm["llamadas"] == 2
    assert llm["llamadas_sin_tokens_reportados"] == 1
    assert llm["tokens_entrada"] == 100


def test_cuenta_las_llamadas_por_proveedor():
    """Ver que el primario falla a diario y la reserva sostiene el sistema es
    información que hay que poder mirar."""
    c = ColectorDeMetricas()

    c.registrar_llamada_llm("groq", 10, 5)
    c.registrar_llamada_llm("dashscope", 10, 5)
    c.registrar_llamada_llm("dashscope", 10, 5)

    assert c.resumen()["proveedor_llm"]["por_proveedor"] == {"groq": 1, "dashscope": 2}


def test_el_costo_en_dinero_se_declara_ausente_y_no_se_inventa():
    """Exige el precio por millón de tokens de cada proveedor, que se consulta
    contra su documentación. Un costo inventado es peor que ninguno: se usaría
    para presupuestar."""
    assert ColectorDeMetricas().resumen()["proveedor_llm"]["costo_estimado"] is None


# ── Concurrencia ────────────────────────────────────────────────────────────


def test_no_pierde_registros_con_hilos_simultaneos():
    """Red de regresión, como las demás pruebas de concurrencia del proyecto:
    bajo el GIL la carrera casi nunca se manifiesta. El cerrojo está porque
    el GIL es un detalle de CPython, no una garantía del lenguaje."""
    import threading

    c = ColectorDeMetricas()
    listos = threading.Barrier(8)

    def registrar():
        listos.wait()
        for _ in range(100):
            c.registrar_operacion("op", 1.0)
            c.registrar_clasificacion("modelo", None)

    hilos = [threading.Thread(target=registrar) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert c.resumen()["clasificacion"]["total"] == 800


# ── Integración con la API ──────────────────────────────────────────────────


@pytest.fixture
def cliente_con_metricas():
    import json

    from fastapi.testclient import TestClient

    from mai.adaptadores.llm.falso import AdaptadorFalso
    from mai.api.app import crear_app

    respuesta = json.dumps({"categoria": "Accesos", "prioridad": "Alta"})
    with TestClient(crear_app(proveedor=AdaptadorFalso([respuesta] * 20))) as c:
        yield c


DATOS = {
    "asunto": "No puedo entrar",
    "descripcion": "x",
    "area": "Aplicaciones",
    "solicitante": "u@lafortuna.com",
}


def test_la_api_expone_las_metricas(cliente_con_metricas):
    cliente_con_metricas.post("/solicitudes", json=DATOS)

    cuerpo = cliente_con_metricas.get("/metricas").json()

    assert cuerpo["clasificacion"]["total"] == 1
    assert "POST /solicitudes" in cuerpo["operaciones"]


def test_agrupa_por_plantilla_de_ruta_y_no_por_url_concreta(cliente_con_metricas):
    """Agrupar por URL literal daría una serie de un solo dato por cada
    código de solicitud, y ninguna distribución utilizable."""
    codigo = cliente_con_metricas.post("/solicitudes", json=DATOS).json()["codigo"]
    cliente_con_metricas.get(f"/solicitudes/{codigo}")
    cliente_con_metricas.get(f"/solicitudes/{codigo}")

    operaciones = cliente_con_metricas.get("/metricas").json()["operaciones"]

    assert operaciones["GET /solicitudes/{codigo}"]["cuenta"] == 2
    assert not any(codigo in clave for clave in operaciones)

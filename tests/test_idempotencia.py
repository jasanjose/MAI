"""Pruebas de idempotencia de `POST /solicitudes`.

EL PROBLEMA QUE RESUELVE, que no es «evitar duplicados» en abstracto:

    Cliente ──POST──> API ──crea SOL-000001──> responde
                                                   ✗ la respuesta se pierde

El cliente no sabe si la solicitud existe. Reintenta. Sin idempotencia se
crea SOL-000002 y el usuario ve dos tickets del mismo problema. El defecto no
está en el servidor —hizo exactamente lo que le pidieron dos veces— sino en
que la operación no era repetible sin efecto.

DOS IDENTIFICADORES QUE NO SON LO MISMO:

    SOL-000001    identifica el RECURSO creado
    abc-123       identifica la INTENCIÓN de ejecutar una operación

El primero lo asigna el servidor; el segundo lo genera el cliente antes de
intentar nada, y por eso sobrevive a un reintento.
"""

import json

import pytest
from fastapi.testclient import TestClient

from mai.adaptadores.llm.falso import AdaptadorFalso
from mai.api.app import crear_app

CLAVE = "Idempotency-Key"
CABECERA_REPETIDA = "Idempotency-Replayed"

DATOS = {
    "asunto": "No puedo entrar al sistema",
    "descripcion": "Me pide contraseña y la rechaza",
    "area": "Aplicaciones",
    "solicitante": "usuario001@lafortuna.com.co",
}

OTROS_DATOS = {
    "asunto": "Solicito vacaciones",
    "descripcion": "Del 1 al 15 de diciembre",
    "area": "Talento Humano",
    "solicitante": "usuario001@lafortuna.com.co",
}


def respuestas(n=20):
    return [json.dumps({"categoria": "Accesos", "prioridad": "Alta"})] * n


@pytest.fixture
def proveedor():
    return AdaptadorFalso(respuestas())


@pytest.fixture
def cliente(proveedor):
    with TestClient(crear_app(proveedor=proveedor)) as c:
        yield c


# ── El caso central ─────────────────────────────────────────────────────────


def test_repetir_la_peticion_con_la_misma_clave_no_crea_un_segundo_recurso(cliente):
    primera = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    segunda = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert primera.json()["codigo"] == segunda.json()["codigo"]
    assert cliente.get("/solicitudes").json()["total"] == 1


def test_la_repeticion_se_declara_en_una_cabecera(cliente):
    """El cliente debe poder distinguir «se creó» de «ya estaba», aunque el
    cuerpo sea idéntico. Sin la cabecera no tiene forma de saberlo."""
    primera = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    segunda = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert CABECERA_REPETIDA not in primera.headers
    assert segunda.headers[CABECERA_REPETIDA] == "true"


def test_la_repeticion_devuelve_el_mismo_estado_que_la_original(cliente):
    """201 las dos veces: el estado describe el resultado de la OPERACIÓN, y
    la operación creó el recurso. Devolver 200 en la repetición obligaría al
    cliente a tratar dos códigos distintos para el mismo desenlace."""
    primera = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    segunda = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert primera.status_code == 201
    assert segunda.status_code == 201


def test_la_repeticion_devuelve_el_cuerpo_completo_de_la_original(cliente):
    primera = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    segunda = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert primera.json() == segunda.json()


def test_la_repeticion_no_vuelve_a_llamar_al_modelo(cliente, proveedor):
    """Aquí la idempotencia no solo evita un duplicado: evita pagar dos veces
    por la misma clasificación. Cada llamada al proveedor cuesta dinero."""
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    llamadas_tras_la_primera = len(proveedor.llamadas)

    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert len(proveedor.llamadas) == llamadas_tras_la_primera


# ── Lo que NO debe deduplicar ───────────────────────────────────────────────


def test_claves_distintas_crean_recursos_distintos(cliente):
    primera = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})
    segunda = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "xyz-789"})

    assert primera.json()["codigo"] != segunda.json()["codigo"]
    assert cliente.get("/solicitudes").json()["total"] == 2


def test_sin_clave_no_hay_deduplicacion(cliente):
    """La cabecera es opcional. Dos peticiones idénticas sin clave son dos
    solicitudes: puede que el usuario tenga de verdad dos problemas iguales,
    y el servidor no tiene forma de distinguirlo."""
    cliente.post("/solicitudes", json=DATOS)
    cliente.post("/solicitudes", json=DATOS)

    assert cliente.get("/solicitudes").json()["total"] == 2


# ── La misma clave con otro contenido ───────────────────────────────────────


def test_la_misma_clave_con_otro_contenido_responde_409(cliente):
    """No es un reintento: es un error del cliente.

    Devolver la solicitud original sería peor que fallar — el cliente creería
    que se registró su petición de vacaciones y lo que existe es una de
    accesos. Un conflicto declarado es recuperable; una confusión silenciosa
    no.
    """
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    respuesta = cliente.post("/solicitudes", json=OTROS_DATOS, headers={CLAVE: "abc-123"})

    assert respuesta.status_code == 409
    assert respuesta.json()["codigo"] == "CLAVE_IDEMPOTENCIA_REUTILIZADA"


def test_el_conflicto_no_crea_ni_modifica_nada(cliente):
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    cliente.post("/solicitudes", json=OTROS_DATOS, headers={CLAVE: "abc-123"})

    listado = cliente.get("/solicitudes").json()
    assert listado["total"] == 1
    assert listado["datos"][0]["area"] == "Aplicaciones"


def test_el_conflicto_tiene_la_forma_uniforme_de_error(cliente):
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    respuesta = cliente.post("/solicitudes", json=OTROS_DATOS, headers={CLAVE: "abc-123"})

    assert set(respuesta.json()) == {"codigo", "mensaje", "detalle", "id_traza"}


def test_un_cambio_minimo_en_el_contenido_ya_es_otro_contenido(cliente):
    """La huella cubre el cuerpo entero, no una selección de campos."""
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    respuesta = cliente.post(
        "/solicitudes",
        json={**DATOS, "descripcion": DATOS["descripcion"] + "."},
        headers={CLAVE: "abc-123"},
    )

    assert respuesta.status_code == 409


def test_el_orden_de_las_claves_del_json_no_cambia_la_huella(cliente):
    """Dos serializaciones del mismo objeto son la misma petición. Si el
    orden importara, un cliente que use un diccionario sin orden estable
    perdería la idempotencia sin haber cambiado nada."""
    cliente.post(
        "/solicitudes",
        json={"asunto": DATOS["asunto"], "descripcion": DATOS["descripcion"],
              "area": DATOS["area"], "solicitante": DATOS["solicitante"]},
        headers={CLAVE: "abc-123"},
    )

    respuesta = cliente.post(
        "/solicitudes",
        json={"solicitante": DATOS["solicitante"], "area": DATOS["area"],
              "descripcion": DATOS["descripcion"], "asunto": DATOS["asunto"]},
        headers={CLAVE: "abc-123"},
    )

    assert respuesta.status_code == 201
    assert CABECERA_REPETIDA in respuesta.headers


# ── Interacción con la validación ───────────────────────────────────────────


def test_una_peticion_invalida_no_consume_la_clave(cliente):
    """Si un 422 quemara la clave, el cliente no podría corregir sus datos y
    reintentar con la misma: quedaría atrapado en un conflicto permanente."""
    invalida = cliente.post(
        "/solicitudes", json={**DATOS, "area": "Mercadeo"}, headers={CLAVE: "abc-123"}
    )
    assert invalida.status_code == 422

    corregida = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "abc-123"})

    assert corregida.status_code == 201
    assert CABECERA_REPETIDA not in corregida.headers


# ── Concurrencia ────────────────────────────────────────────────────────────


def test_peticiones_simultaneas_con_la_misma_clave_crean_un_solo_recurso(cliente):
    """Red de regresión. NO es una demostración de la carrera, y conviene
    decirlo antes de que alguien la lea como si lo fuera.

    Se midió: se sustituyó el registro por uno que consulta y escribe en dos
    pasos —el error clásico— y esta prueba **siguió pasando** en las tres
    corridas. Dos causas se suman: el GIL de CPython cambia de hilo en
    fronteras de bytecode, y `TestClient` encima hace pasar las peticiones
    por un solo bucle de eventos, así que a nivel HTTP no llegan a solaparse.

    Que la prueba no la vea no significa que la carrera no exista. Llamando a
    `reservar` directamente, con 64 hilos y 500 claves, la versión sin cerrojo
    devolvió `NUEVA` 501 veces para 500 claves: un duplicado. En una de dos
    corridas. Es decir, ocurre de verdad y ocurre poco — que es exactamente el
    perfil de defecto que llega a producción y nadie logra reproducir.

    Por eso el cerrojo está y la prueba se queda como guarda: detecta un
    refactor que rompa el flujo por completo, y fija el contrato de que ocho
    peticiones con la misma clave producen un solo recurso.
    """
    import threading

    resultados: list[int] = []
    cerrojo = threading.Lock()
    listos = threading.Barrier(8)

    def enviar():
        listos.wait()
        respuesta = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "misma-clave"})
        with cerrojo:
            resultados.append(respuesta.status_code)

    hilos = [threading.Thread(target=enviar) for _ in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert cliente.get("/solicitudes").json()["total"] == 1
    assert all(codigo in (201, 409) for codigo in resultados)


# ── Validación de la propia clave ───────────────────────────────────────────


def test_una_clave_vacia_se_trata_como_ausente(cliente):
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "   "})
    cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "   "})

    assert cliente.get("/solicitudes").json()["total"] == 2


def test_una_clave_desmedida_se_rechaza(cliente):
    """Sin cota, un cliente llena la memoria del servidor con claves."""
    respuesta = cliente.post("/solicitudes", json=DATOS, headers={CLAVE: "x" * 500})

    assert respuesta.status_code == 422

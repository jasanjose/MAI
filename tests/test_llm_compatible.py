"""Pruebas del adaptador de proveedores compatibles con Chat Completions.

Ninguna toca la red: se simula el transporte de `httpx`. Eso permite provocar
a voluntad los fallos que un proveedor real produce al azar —límite de tasa,
cortes, respuestas malformadas— en vez de esperar a que ocurran.
"""

import json

import httpx
import pytest

from mai.adaptadores.llm.compatible import AdaptadorCompatible
from mai.dominio.puertos import ProveedorLLM, ProveedorNoDisponible, RespuestaInutilizable


class EsperaFalsa:
    """Registra cuánto se habría esperado, sin esperar."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def cuerpo_ok(texto="respuesta", entrada=11, salida=7):
    datos = {"choices": [{"message": {"content": texto}}]}
    if entrada is not None:
        datos["usage"] = {"prompt_tokens": entrada, "completion_tokens": salida}
    return datos


def construir(manejador, espera=None, reintentos=3):
    return AdaptadorCompatible(
        nombre="proveedor-de-prueba",
        base_url="https://api.proveedor.test/v1",
        api_key="clave-de-prueba",
        modelo="modelo-de-prueba",
        reintentos=reintentos,
        dormir=espera or EsperaFalsa(),
        transporte=httpx.MockTransport(manejador),
    )


def responder_siempre(respuesta: httpx.Response):
    def manejador(peticion: httpx.Request) -> httpx.Response:
        manejador.peticiones.append(peticion)
        return respuesta

    manejador.peticiones = []
    return manejador


def responder_en_secuencia(*respuestas):
    pendientes = list(respuestas)

    def manejador(peticion: httpx.Request) -> httpx.Response:
        manejador.peticiones.append(peticion)
        return pendientes.pop(0) if pendientes else respuestas[-1]

    manejador.peticiones = []
    return manejador


# ── Contrato y camino normal ────────────────────────────────────────────────


def test_cumple_el_contrato_del_puerto():
    with construir(responder_siempre(httpx.Response(200, json=cuerpo_ok()))) as proveedor:
        assert isinstance(proveedor, ProveedorLLM)


def test_devuelve_el_texto_del_modelo():
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok("Accesos")))

    with construir(manejador) as proveedor:
        assert proveedor.completar("instrucción", "entrada").texto == "Accesos"


def test_reporta_los_tokens_que_informa_el_proveedor():
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok(entrada=120, salida=8)))

    with construir(manejador) as proveedor:
        respuesta = proveedor.completar("i", "e")

    assert respuesta.tokens_entrada == 120
    assert respuesta.tokens_salida == 8
    assert respuesta.latencia_ms >= 0


def test_declara_los_tokens_ausentes_cuando_el_proveedor_no_los_informa():
    """`usage` es opcional y varios proveedores lo omiten. Un cero fingido
    haría parecer gratis lo que no lo fue."""
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok(entrada=None)))

    with construir(manejador) as proveedor:
        respuesta = proveedor.completar("i", "e")

    assert respuesta.tokens_entrada is None
    assert respuesta.tokens_salida is None


# ── Seguridad: los dos canales y la credencial ──────────────────────────────


def test_la_instruccion_y_la_entrada_viajan_en_roles_distintos():
    """La mitad de la defensa contra inyección de prompt vive aquí.

    Si algún día alguien juntara los dos textos en un solo mensaje, el modelo
    dejaría de poder distinguir la orden del sistema del texto del usuario.
    """
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok()))

    with construir(manejador) as proveedor:
        proveedor.completar("soy el sistema", "soy el usuario")

    enviado = json.loads(manejador.peticiones[0].content)
    assert enviado["messages"] == [
        {"role": "system", "content": "soy el sistema"},
        {"role": "user", "content": "soy el usuario"},
    ]


def test_pide_temperatura_cero_para_que_el_resultado_sea_reproducible():
    """Una clasificación que cambia entre ejecuciones no se puede evaluar
    contra un conjunto de referencia."""
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok()))

    with construir(manejador) as proveedor:
        proveedor.completar("i", "e")

    assert json.loads(manejador.peticiones[0].content)["temperature"] == 0.0


def test_la_credencial_viaja_en_la_cabecera_y_no_en_el_cuerpo():
    manejador = responder_siempre(httpx.Response(200, json=cuerpo_ok()))

    with construir(manejador) as proveedor:
        proveedor.completar("i", "e")

    peticion = manejador.peticiones[0]
    assert peticion.headers["Authorization"] == "Bearer clave-de-prueba"
    assert "clave-de-prueba" not in peticion.content.decode()


def test_el_mensaje_de_error_nunca_incluye_la_credencial():
    """Un registro con una credencial dentro es un secreto filtrado.
    Algunos proveedores la devuelven enmascarada en el cuerpo del error."""
    manejador = responder_siempre(
        httpx.Response(401, json={"error": "clave inválida: clave-de-prueba"})
    )

    with construir(manejador) as proveedor, pytest.raises(ProveedorNoDisponible) as error:
        proveedor.completar("i", "e")

    assert "clave-de-prueba" not in str(error.value)


# ── Robustez ante fallos ────────────────────────────────────────────────────


def test_reintenta_ante_un_error_del_servidor_y_termina_respondiendo():
    manejador = responder_en_secuencia(
        httpx.Response(500),
        httpx.Response(200, json=cuerpo_ok("al fin")),
    )

    with construir(manejador) as proveedor:
        assert proveedor.completar("i", "e").texto == "al fin"

    assert len(manejador.peticiones) == 2


def test_respeta_el_retry_after_que_indica_el_proveedor():
    espera = EsperaFalsa()
    manejador = responder_en_secuencia(
        httpx.Response(429, headers={"Retry-After": "4"}),
        httpx.Response(200, json=cuerpo_ok()),
    )

    with construir(manejador, espera=espera) as proveedor:
        proveedor.completar("i", "e")

    assert espera.esperas == [4.0]


def test_falla_con_mensaje_legible_tras_agotar_los_reintentos():
    """Estándar §3: nunca una excepción cruda de la librería hacia el dominio."""
    manejador = responder_siempre(httpx.Response(503))

    with construir(manejador, reintentos=2) as proveedor, pytest.raises(
        ProveedorNoDisponible
    ) as error:
        proveedor.completar("i", "e")

    assert len(manejador.peticiones) == 2
    assert "Se intentó 2 veces" in str(error.value)


def test_no_reintenta_una_credencial_invalida():
    """Reintentar un 401 gasta tiempo y cuota para el mismo resultado."""
    manejador = responder_siempre(httpx.Response(401))

    with construir(manejador) as proveedor, pytest.raises(ProveedorNoDisponible):
        proveedor.completar("i", "e")

    assert len(manejador.peticiones) == 1


def test_no_reintenta_un_modelo_inexistente():
    manejador = responder_siempre(httpx.Response(404))

    with construir(manejador) as proveedor, pytest.raises(ProveedorNoDisponible) as error:
        proveedor.completar("i", "e")

    assert len(manejador.peticiones) == 1
    assert "modelo-de-prueba" in str(error.value)


def test_traduce_un_tiempo_de_espera_agotado():
    def manejador(_peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("agotado")

    with construir(manejador, reintentos=1) as proveedor, pytest.raises(
        ProveedorNoDisponible
    ) as error:
        proveedor.completar("i", "e")

    assert "tiempo de espera" in str(error.value)


# ── Respuestas malformadas ──────────────────────────────────────────────────


def test_rechaza_una_respuesta_sin_la_forma_esperada():
    manejador = responder_siempre(httpx.Response(200, json={"otra_cosa": True}))

    with construir(manejador) as proveedor, pytest.raises(RespuestaInutilizable):
        proveedor.completar("i", "e")


def test_rechaza_un_cuerpo_que_no_es_json():
    manejador = responder_siempre(httpx.Response(200, content=b"no soy json"))

    with construir(manejador) as proveedor, pytest.raises(RespuestaInutilizable):
        proveedor.completar("i", "e")


def test_rechaza_un_contenido_que_no_es_texto():
    """Caso de borde: `content` puede venir null si el modelo se corta."""
    manejador = responder_siempre(
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    )

    with construir(manejador) as proveedor, pytest.raises(RespuestaInutilizable):
        proveedor.completar("i", "e")


def test_no_reintenta_una_respuesta_malformada():
    """Reintentar una respuesta ilegible da otra respuesta ilegible."""
    manejador = responder_siempre(httpx.Response(200, json={"otra_cosa": True}))

    with construir(manejador) as proveedor, pytest.raises(RespuestaInutilizable):
        proveedor.completar("i", "e")

    assert len(manejador.peticiones) == 1


# ── Configuración ───────────────────────────────────────────────────────────


def test_rechaza_construirse_sin_url_base():
    """Falla al construir, no en la primera llamada en producción."""
    with pytest.raises(ValueError, match="base_url"):
        AdaptadorCompatible(nombre="x", base_url="", api_key="k", modelo="m")


def test_rechaza_construirse_sin_modelo():
    with pytest.raises(ValueError, match="modelo"):
        AdaptadorCompatible(nombre="x", base_url="https://a.test", api_key="k", modelo="  ")

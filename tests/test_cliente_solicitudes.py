"""Pruebas del cliente del servicio externo.

Ninguna toca la red: se simula el transporte de httpx. Eso permite provocar
a voluntad los fallos que el servicio real produce al azar —12 % de 500 y
5 % de 429— en vez de esperar a que ocurran.
"""

import httpx
import pytest

from mai.adaptadores.http.cliente_solicitudes import (
    ClienteSolicitudes,
    NoAutorizado,
    RecursoNoEncontrado,
    ServicioNoDisponible,
    SolicitudInvalida,
)


class EsperaFalsa:
    """Registra cuánto se habría esperado, sin esperar."""

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def construir_cliente(manejador, espera=None, reintentos=3):
    return ClienteSolicitudes(
        url_base="http://servicio-de-prueba",
        token="token-de-prueba",
        reintentos=reintentos,
        dormir=espera or EsperaFalsa(),
        transporte=httpx.MockTransport(manejador),
    )


def respuestas_en_secuencia(*respuestas):
    """Devuelve una respuesta distinta por llamada, en orden."""
    pendientes = list(respuestas)

    def manejador(peticion: httpx.Request) -> httpx.Response:
        manejador.peticiones.append(peticion)
        return pendientes.pop(0) if pendientes else respuestas[-1]

    manejador.peticiones = []
    return manejador


# ── Camino normal ───────────────────────────────────────────────────────────


def test_consulta_la_salud_del_servicio():
    manejador = respuestas_en_secuencia(httpx.Response(200, json={"estado": "operativo"}))
    with construir_cliente(manejador) as cliente:
        assert cliente.salud()["estado"] == "operativo"


def test_lista_solicitudes_y_pasa_los_filtros():
    manejador = respuestas_en_secuencia(httpx.Response(200, json=[{"id": "EXT-1"}]))
    with construir_cliente(manejador) as cliente:
        resultado = cliente.listar_solicitudes(area="Compras", estado="Abierto", limite=10)
    assert resultado == [{"id": "EXT-1"}]
    consulta = manejador.peticiones[0].url.params
    assert consulta["area"] == "Compras"
    assert consulta["estado"] == "Abierto"


def test_crear_solicitud_envia_la_clave_de_idempotencia():
    """Sin esta cabecera, un 500 devuelto DESPUÉS de que el servicio ya creó
    el registro produciría un duplicado en el reintento."""
    manejador = respuestas_en_secuencia(httpx.Response(201, json={"id": "EXT-9"}))
    with construir_cliente(manejador) as cliente:
        cliente.crear_solicitud(
            asunto="No enciende el portátil",
            area="Aplicaciones",
            solicitante="usuario001@lafortuna.com.co",
            clave_idempotencia="clave-fija-123",
        )
    assert manejador.peticiones[0].headers["Idempotency-Key"] == "clave-fija-123"


# ── El servicio falla a propósito ───────────────────────────────────────────


def test_reintenta_el_500_y_termina_bien_si_el_servicio_se_recupera():
    manejador = respuestas_en_secuencia(
        httpx.Response(500, json={"detail": "Error interno"}),
        httpx.Response(500, json={"detail": "Error interno"}),
        httpx.Response(200, json={"estado": "operativo"}),
    )
    with construir_cliente(manejador) as cliente:
        assert cliente.salud()["estado"] == "operativo"
    assert len(manejador.peticiones) == 3


def test_respeta_el_retry_after_que_indica_el_servicio_en_el_429():
    """Si el servicio dice cuánto esperar, se le hace caso: sabe más que
    nosotros sobre su propia recuperación."""
    espera = EsperaFalsa()
    manejador = respuestas_en_secuencia(
        httpx.Response(429, headers={"Retry-After": "3"}, json={"detail": "límite"}),
        httpx.Response(200, json={"estado": "operativo"}),
    )
    with construir_cliente(manejador, espera=espera) as cliente:
        cliente.salud()
    assert espera.esperas == [3.0]


def test_el_retroceso_es_exponencial_cuando_el_servicio_no_indica_nada():
    espera = EsperaFalsa()
    manejador = respuestas_en_secuencia(httpx.Response(500), httpx.Response(500),
                                        httpx.Response(200, json={}))
    with construir_cliente(manejador, espera=espera) as cliente:
        cliente.salud()
    assert len(espera.esperas) == 2
    assert espera.esperas[1] > espera.esperas[0]  # cada espera es mayor que la anterior


def test_no_reintenta_los_errores_que_no_se_resuelven_solos():
    """Reintentar un 401 gasta tiempo y cuota para obtener el mismo 401."""
    manejador = respuestas_en_secuencia(httpx.Response(401, json={"detail": "Token inválido"}))
    with construir_cliente(manejador) as cliente, pytest.raises(NoAutorizado):
        cliente.salud()
    assert len(manejador.peticiones) == 1


def test_el_recurso_inexistente_se_distingue_del_servicio_caido():
    manejador = respuestas_en_secuencia(httpx.Response(404, json={"detail": "no existe"}))
    with construir_cliente(manejador) as cliente, pytest.raises(RecursoNoEncontrado):
        cliente.obtener_solicitud("EXT-INEXISTENTE")


def test_agotados_los_reintentos_falla_con_un_mensaje_que_una_persona_entiende():
    manejador = respuestas_en_secuencia(httpx.Response(500), httpx.Response(500),
                                        httpx.Response(500))
    with construir_cliente(manejador) as cliente:
        with pytest.raises(ServicioNoDisponible) as error:
            cliente.salud()
    mensaje = str(error.value)
    assert "500" in mensaje
    assert "3 veces" in mensaje
    assert "Traceback" not in mensaje  # nunca se filtra una traza al usuario


def test_el_tiempo_de_espera_agotado_no_deja_escapar_la_excepcion_de_la_libreria():
    def manejador(_peticion):
        raise httpx.ReadTimeout("tiempo agotado")

    with construir_cliente(manejador) as cliente:
        with pytest.raises(ServicioNoDisponible) as error:
            cliente.salud()
    assert "tiempo de espera" in str(error.value)


def test_el_servicio_caido_se_traduce_a_un_error_del_dominio():
    def manejador(_peticion):
        raise httpx.ConnectError("conexión rechazada")

    with construir_cliente(manejador) as cliente:
        with pytest.raises(ServicioNoDisponible) as error:
            cliente.salud()
    assert "conexión" in str(error.value)


def test_un_cuerpo_que_no_es_json_no_revienta_el_proceso():
    manejador = respuestas_en_secuencia(httpx.Response(200, text="<html>error</html>"))
    with construir_cliente(manejador) as cliente, pytest.raises(ServicioNoDisponible):
        cliente.salud()


# ── Casos de borde y medición ───────────────────────────────────────────────


def test_pedir_una_solicitud_sin_identificador_se_rechaza_antes_de_salir_a_la_red():
    manejador = respuestas_en_secuencia(httpx.Response(200, json={}))
    with construir_cliente(manejador) as cliente, pytest.raises(SolicitudInvalida):
        cliente.obtener_solicitud("   ")
    assert manejador.peticiones == []


def test_toda_llamada_registra_latencia_intentos_y_resultado():
    """El estándar §7 lo exige: lo que no se mide no se puede sostener."""
    manejador = respuestas_en_secuencia(httpx.Response(500), httpx.Response(200, json={}))
    with construir_cliente(manejador) as cliente:
        cliente.salud()
    medicion = cliente.mediciones[-1]
    assert medicion.operacion == "salud"
    assert medicion.resultado == "exito"
    assert medicion.intentos == 2
    assert medicion.latencia_ms >= 0


def test_tambien_se_mide_la_llamada_que_termina_en_error():
    manejador = respuestas_en_secuencia(httpx.Response(500), httpx.Response(500),
                                        httpx.Response(500))
    with construir_cliente(manejador) as cliente:
        with pytest.raises(ServicioNoDisponible):
            cliente.salud()
    assert cliente.mediciones[-1].resultado == "error"

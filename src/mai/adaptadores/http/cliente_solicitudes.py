"""Cliente del servicio externo de solicitudes corporativas.

El servicio **falla a propósito**: latencia de 0,1 a 2,5 s, 12 % de
respuestas 500 y 5 % de 429 con cabecera `Retry-After`. Eso no es un
problema del material: manejarlo es el trabajo.

Tres reglas que este adaptador cumple sin excepción, según el estándar §3:

1. Ninguna llamada de red sin tiempo de espera explícito.
2. Reintento con retroceso exponencial, respetando `Retry-After`.
3. Nunca propaga una excepción cruda de la librería: la traduce a un error
   del dominio con un mensaje que una persona puede leer.

El reintento está escrito a mano y no delegado a una librería. Son quince
líneas, y quien las mantiene debe poder explicar por qué reintenta un 500 y
no un 404.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from mai.adaptadores.reintento import ESPERA_MAXIMA_S, calcular_espera, leer_retry_after

logger = logging.getLogger(__name__)

TIEMPO_ESPERA_S = 10.0
REINTENTOS = 3
ESPERA_BASE_S = 0.5

# Un 500 o un 429 pueden resolverse solos; un 401 o un 404 no. Reintentar un
# error del cliente solo gasta tiempo y cuota para obtener el mismo resultado.
CODIGOS_REINTENTABLES = frozenset({429, 500, 502, 503, 504})


class ErrorServicioExterno(Exception):
    """Base de los fallos del servicio externo, ya traducidos a lenguaje claro."""


class ServicioNoDisponible(ErrorServicioExterno):
    """El servicio no respondió correctamente tras agotar los reintentos."""


class NoAutorizado(ErrorServicioExterno):
    """Token ausente o inválido."""


class RecursoNoEncontrado(ErrorServicioExterno):
    """La solicitud consultada no existe."""


class SolicitudInvalida(ErrorServicioExterno):
    """El servicio rechazó los datos enviados."""


@dataclass(frozen=True)
class Medicion:
    """Lo que hay que registrar de toda llamada externa (estándar §7)."""

    operacion: str
    latencia_ms: float
    intentos: int
    resultado: str  # "exito" | "error"
    codigo_estado: int | None = None


class ClienteSolicitudes:
    """Cliente del servicio de solicitudes.

    Recibe la URL base y el token por parámetro; nunca los lee del código.
    Se usa como gestor de contexto para garantizar el cierre de la conexión:

        with ClienteSolicitudes(url, token) as cliente:
            cliente.salud()

    Ante fallo lanza una subclase de `ErrorServicioExterno` con un mensaje
    legible. Nunca deja escapar una excepción de `httpx`.
    """

    def __init__(
        self,
        url_base: str,
        token: str,
        tiempo_espera_s: float = TIEMPO_ESPERA_S,
        reintentos: int = REINTENTOS,
        espera_base_s: float = ESPERA_BASE_S,
        dormir: Callable[[float], None] = time.sleep,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        self._url_base = url_base.rstrip("/")
        self._reintentos = max(1, reintentos)
        self._espera_base_s = espera_base_s
        # Inyectable para que las pruebas no esperen de verdad.
        self._dormir = dormir
        # `transporte` existe para que las pruebas simulen respuestas del
        # servicio sin tocar la red. En producción va en None y httpx usa el suyo.
        self._cliente = httpx.Client(
            timeout=tiempo_espera_s,
            headers={"Authorization": f"Bearer {token}"},
            transport=transporte,
        )
        self.mediciones: list[Medicion] = []

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    def __enter__(self) -> ClienteSolicitudes:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        self._cliente.close()

    # ── Operaciones ─────────────────────────────────────────────────────────

    def salud(self) -> dict[str, Any]:
        """Sonda del servicio. Es la única ruta que el mock no hace fallar."""
        return self._pedir("GET", "/health", "salud")

    def listar_solicitudes(
        self,
        area: str | None = None,
        estado: str | None = None,
        limite: int = 50,
    ) -> list[dict[str, Any]]:
        """Lista solicitudes con filtros opcionales. Devuelve [] si no hay."""
        parametros: dict[str, Any] = {"limite": limite}
        if area:
            parametros["area"] = area
        if estado:
            parametros["estado"] = estado
        datos = self._pedir("GET", "/solicitudes", "listar", parametros=parametros)
        return datos if isinstance(datos, list) else []

    def obtener_solicitud(self, id_solicitud: str) -> dict[str, Any]:
        """Consulta una solicitud por su identificador."""
        if not str(id_solicitud).strip():
            raise SolicitudInvalida("Se pidió una solicitud sin identificador.")
        return self._pedir("GET", f"/solicitudes/{id_solicitud}", "obtener")

    def crear_solicitud(
        self,
        asunto: str,
        area: str,
        solicitante: str,
        descripcion: str = "",
        canal: str = "api",
        clave_idempotencia: str | None = None,
    ) -> dict[str, Any]:
        """Crea una solicitud en el servicio externo.

        `clave_idempotencia` viaja como cabecera `Idempotency-Key`: dos
        peticiones con la misma clave devuelven la misma solicitud en vez de
        crear dos. Importa porque este cliente reintenta: sin la clave, un
        500 devuelto *después* de que el servicio ya creó el registro
        produciría un duplicado en el reintento.
        """
        cuerpo = {
            "asunto": asunto,
            "descripcion": descripcion,
            "area": area,
            "solicitante": solicitante,
            "canal": canal,
        }
        cabeceras = {"Idempotency-Key": clave_idempotencia} if clave_idempotencia else None
        return self._pedir("POST", "/solicitudes", "crear", cuerpo=cuerpo, cabeceras=cabeceras)

    # ── Motor de peticiones con reintento ───────────────────────────────────

    def _pedir(
        self,
        metodo: str,
        ruta: str,
        operacion: str,
        parametros: dict[str, Any] | None = None,
        cuerpo: dict[str, Any] | None = None,
        cabeceras: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self._url_base}{ruta}"
        inicio = time.monotonic()
        ultimo_motivo = "el servicio no respondió"
        ultimo_codigo: int | None = None
        ultima_respuesta: httpx.Response | None = None

        for intento in range(1, self._reintentos + 1):
            ultima_respuesta = None
            try:
                respuesta = self._cliente.request(
                    metodo, url, params=parametros, json=cuerpo, headers=cabeceras
                )
            except httpx.TimeoutException:
                ultimo_motivo = "se agotó el tiempo de espera"
            except httpx.TransportError:
                ultimo_motivo = "no se pudo establecer la conexión"
            else:
                ultima_respuesta = respuesta
                ultimo_codigo = respuesta.status_code
                if respuesta.status_code < 400:
                    self._medir(operacion, inicio, intento, "exito", respuesta.status_code)
                    return self._leer_cuerpo(respuesta, operacion)

                self._traducir_error_no_reintentable(respuesta)
                ultimo_motivo = f"el servicio respondió {respuesta.status_code}"

            if intento < self._reintentos:
                self._dormir(self._calcular_espera(intento, ultima_respuesta))

        self._medir(operacion, inicio, self._reintentos, "error", ultimo_codigo)
        raise ServicioNoDisponible(
            f"No se pudo completar la operación «{operacion}»: {ultimo_motivo}. "
            f"Se intentó {self._reintentos} veces. Intente más tarde o revise "
            f"si el servicio está en línea."
        )

    def _traducir_error_no_reintentable(self, respuesta: httpx.Response) -> None:
        """Convierte los errores que no van a resolverse solos.

        Se lanzan de inmediato: reintentar un 401 o un 404 gasta tiempo para
        obtener exactamente la misma respuesta.
        """
        if respuesta.status_code in CODIGOS_REINTENTABLES:
            return
        if respuesta.status_code == 401:
            raise NoAutorizado(
                "El servicio rechazó las credenciales. Revise que MAI_MOCK_TOKEN "
                "esté configurado y sea el vigente."
            )
        if respuesta.status_code == 404:
            raise RecursoNoEncontrado("El servicio no encontró la solicitud consultada.")
        if 400 <= respuesta.status_code < 500:
            raise SolicitudInvalida(
                f"El servicio rechazó los datos enviados (código {respuesta.status_code})."
            )

    def _calcular_espera(self, intento: int, respuesta: httpx.Response | None) -> float:
        """Retroceso exponencial, con `Retry-After` por encima si el servicio lo indica.

        Lo único propio de este adaptador es saber DÓNDE viene esa indicación:
        la cabecera `Retry-After` de una respuesta 429. La matemática del
        retroceso es común con el adaptador del proveedor de lenguaje y vive
        en `mai.adaptadores.reintento`.
        """
        indicada = None
        if respuesta is not None and respuesta.status_code == 429:
            indicada = leer_retry_after(respuesta.headers.get("Retry-After"))

        return calcular_espera(
            intento,
            self._espera_base_s,
            espera_indicada_s=indicada,
            espera_maxima_s=ESPERA_MAXIMA_S,
        )

    def _leer_cuerpo(self, respuesta: httpx.Response, operacion: str) -> Any:
        try:
            return respuesta.json()
        except ValueError as error:
            raise ServicioNoDisponible(
                f"El servicio respondió a «{operacion}» con un cuerpo que no es JSON válido."
            ) from error

    def _medir(
        self, operacion: str, inicio: float, intentos: int, resultado: str, codigo: int | None
    ) -> None:
        medicion = Medicion(
            operacion=operacion,
            latencia_ms=round((time.monotonic() - inicio) * 1000, 2),
            intentos=intentos,
            resultado=resultado,
            codigo_estado=codigo,
        )
        self.mediciones.append(medicion)
        logger.info(
            "llamada_externa",
            extra={
                "operacion": medicion.operacion,
                "latencia_ms": medicion.latencia_ms,
                "intentos": medicion.intentos,
                "resultado": medicion.resultado,
                "codigo_estado": medicion.codigo_estado,
            },
        )

"""Adaptador para proveedores que hablan la API Chat Completions.

**Un solo archivo para cinco proveedores.** OpenAI, Groq, DashScope,
OpenRouter y Ollama exponen la misma forma: `POST /chat/completions` con una
lista de mensajes por rol. Lo único que cambia entre ellos es `base_url`,
`api_key` y `model`. Escribir un adaptador por proveedor produciría cinco
archivos casi idénticos, cinco veces la misma lógica de reintento y cinco
superficies distintas que mantener (ADR-004 §B).

Queda fuera Anthropic, que no habla esta forma. Entraría vía OpenRouter.

Los dos mensajes van por roles distintos **y eso es la mitad de la defensa
contra inyección de prompt**: la instrucción va como `system`, el texto del
usuario como `user`. La otra mitad —delimitar y ordenar que se trate como
dato— la pone el dominio, que es quien escribe la instrucción.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from mai.adaptadores.reintento import calcular_espera, leer_retry_after
from mai.dominio.puertos import (
    ProveedorLLM,
    ProveedorNoDisponible,
    RespuestaInutilizable,
    RespuestaLLM,
)

logger = logging.getLogger(__name__)

TIEMPO_ESPERA_S = 30.0
REINTENTOS = 3
ESPERA_BASE_S = 0.5

# Un 429 o un 5xx pueden resolverse solos. Un 401 (credencial mala) o un 404
# (modelo inexistente) no: reintentarlos gasta tiempo y cuota para obtener
# exactamente el mismo resultado.
CODIGOS_REINTENTABLES = frozenset({408, 429, 500, 502, 503, 504})

# Temperatura cero: las dos tareas del sistema —clasificar y responder
# citando políticas— buscan reproducibilidad, no variedad. Una clasificación
# que cambia entre ejecuciones no se puede evaluar contra un conjunto de
# referencia.
TEMPERATURA = 0.0


class AdaptadorCompatible(ProveedorLLM):
    """Proveedor de lenguaje sobre la API Chat Completions.

    `transporte` existe para que las pruebas simulen respuestas sin tocar la
    red; en producción va en None y `httpx` usa el suyo. `dormir` se inyecta
    para que las pruebas del reintento no esperen de verdad.

    La credencial se recibe por parámetro y **nunca** se registra ni se
    incluye en un mensaje de error. Quien la pasa la lee del entorno.
    """

    def __init__(
        self,
        nombre: str,
        base_url: str,
        api_key: str,
        modelo: str,
        tiempo_espera_s: float = TIEMPO_ESPERA_S,
        reintentos: int = REINTENTOS,
        espera_base_s: float = ESPERA_BASE_S,
        transporte: httpx.BaseTransport | None = None,
        dormir: Callable[[float], None] = time.sleep,
        cuerpo_extra: dict[str, object] | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError(f"El proveedor «{nombre}» no tiene base_url configurada.")
        if not modelo.strip():
            raise ValueError(f"El proveedor «{nombre}» no tiene modelo configurado.")

        # Ajustes propios del proveedor (ver adaptadores/llm/perfiles.py). Se
        # copia lo recibido: guardar la referencia dejaria que quien la pasó
        # mutara el cuerpo de todas las peticiones siguientes.
        self._cuerpo_extra = dict(cuerpo_extra or {})

        self._nombre = nombre
        self._modelo = modelo
        self._reintentos = max(1, reintentos)
        self._espera_base_s = espera_base_s
        self._dormir = dormir
        self._cliente = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=tiempo_espera_s,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transporte,
        )

    @property
    def nombre(self) -> str:
        return self._nombre

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    def __enter__(self) -> AdaptadorCompatible:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        self._cliente.close()

    # ── Contrato del puerto ─────────────────────────────────────────────────

    def completar(self, instruccion: str, entrada: str) -> RespuestaLLM:
        """Pide una respuesta al modelo, con reintento y medición."""
        cuerpo = {
            # Los ajustes del proveedor van PRIMERO para que las claves de
            # abajo los sobrescriban y no al revés. Un perfil mal escrito puede
            # degradar la petición; no puede cambiar a qué modelo se pregunta
            # ni qué se le manda.
            **self._cuerpo_extra,
            "model": self._modelo,
            "temperature": TEMPERATURA,
            "messages": [
                {"role": "system", "content": instruccion},
                {"role": "user", "content": entrada},
            ],
        }

        inicio = time.monotonic()
        ultimo_motivo = "el proveedor no respondió"

        for intento in range(1, self._reintentos + 1):
            respuesta = None
            try:
                respuesta = self._cliente.post("/chat/completions", json=cuerpo)
            except httpx.TimeoutException:
                ultimo_motivo = "se agotó el tiempo de espera"
            except httpx.TransportError:
                ultimo_motivo = "no se pudo establecer la conexión"
            else:
                if respuesta.status_code < 400:
                    return self._leer(respuesta, inicio)

                self._traducir_error_no_reintentable(respuesta)
                ultimo_motivo = f"el proveedor respondió {respuesta.status_code}"

            if intento < self._reintentos:
                self._dormir(self._calcular_espera(intento, respuesta))

        self._registrar(inicio, "error", None, None)
        raise ProveedorNoDisponible(
            f"El proveedor «{self._nombre}» no respondió: {ultimo_motivo}. "
            f"Se intentó {self._reintentos} veces."
        )

    # ── Interno ─────────────────────────────────────────────────────────────

    def _traducir_error_no_reintentable(self, respuesta: httpx.Response) -> None:
        """Lanza de inmediato los errores que no se resuelven esperando.

        El mensaje NUNCA incluye el cuerpo de la respuesta ni la credencial:
        algunos proveedores devuelven la clave enmascarada en el error, y un
        registro con una credencial dentro es un secreto filtrado.
        """
        if respuesta.status_code in CODIGOS_REINTENTABLES:
            return
        if respuesta.status_code in (401, 403):
            raise ProveedorNoDisponible(
                f"El proveedor «{self._nombre}» rechazó las credenciales. "
                "Revise la variable de entorno correspondiente."
            )
        if respuesta.status_code == 404:
            raise ProveedorNoDisponible(
                f"El proveedor «{self._nombre}» no reconoce el modelo «{self._modelo}»."
            )
        raise RespuestaInutilizable(
            f"El proveedor «{self._nombre}» rechazó la petición "
            f"(código {respuesta.status_code})."
        )

    def _calcular_espera(self, intento: int, respuesta: httpx.Response | None) -> float:
        indicada = None
        if respuesta is not None and respuesta.status_code == 429:
            indicada = leer_retry_after(respuesta.headers.get("Retry-After"))
        return calcular_espera(intento, self._espera_base_s, espera_indicada_s=indicada)

    def _leer(self, respuesta: httpx.Response, inicio: float) -> RespuestaLLM:
        """Extrae el texto y el consumo de tokens de una respuesta correcta."""
        try:
            datos: Any = respuesta.json()
            texto = datos["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            self._registrar(inicio, "error", None, None)
            raise RespuestaInutilizable(
                f"El proveedor «{self._nombre}» respondió con una forma inesperada."
            ) from error

        if not isinstance(texto, str):
            self._registrar(inicio, "error", None, None)
            raise RespuestaInutilizable(
                f"El proveedor «{self._nombre}» devolvió un contenido que no es texto."
            )

        # `usage` es opcional en la especificación y varios proveedores lo
        # omiten. Ausente se declara None, no cero: un cero se suma en los
        # agregados y hace parecer gratis lo que no lo fue.
        uso = datos.get("usage") or {}
        entrada = uso.get("prompt_tokens")
        salida = uso.get("completion_tokens")

        # El desglose es opcional en la especificación. Ausente se declara
        # None, no cero: un cero afirmaría que el modelo no razonó, y lo que
        # se sabe es que no lo informó.
        detalle = uso.get("completion_tokens_details") or {}
        razonamiento = detalle.get("reasoning_tokens") if isinstance(detalle, dict) else None

        latencia_ms = self._registrar(inicio, "exito", entrada, salida)
        return RespuestaLLM(
            texto=texto,
            proveedor=self._nombre,
            modelo=self._modelo,
            latencia_ms=latencia_ms,
            tokens_entrada=entrada if isinstance(entrada, int) else None,
            tokens_salida=salida if isinstance(salida, int) else None,
            tokens_razonamiento=razonamiento if isinstance(razonamiento, int) else None,
        )

    def _registrar(
        self, inicio: float, resultado: str, entrada: int | None, salida: int | None
    ) -> float:
        """Registro estructurado de la llamada. Estándar §7.

        No lleva el texto del ticket ni la respuesta: identificadores y
        medidas, nunca contenido.
        """
        latencia_ms = round((time.monotonic() - inicio) * 1000, 2)
        logger.info(
            "llamada_llm",
            extra={
                "proveedor": self._nombre,
                "modelo": self._modelo,
                "latencia_ms": latencia_ms,
                "tokens_entrada": entrada,
                "tokens_salida": salida,
                "resultado": resultado,
            },
        )
        return latencia_ms

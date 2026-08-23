"""Forma uniforme de error de la API.

Toda respuesta de error de esta API tiene exactamente esta forma, sin
excepción (estándar §4):

    {"codigo": "...", "mensaje": "...", "detalle": {}, "id_traza": "..."}

Que sea uniforme importa más de lo que parece: un cliente que recibe tres
formas distintas de error termina analizando texto libre para saber qué pasó,
y ese análisis se rompe con cada cambio de redacción.

**Nunca sale una traza de excepción hacia el cliente.** Una traza revela
rutas del sistema de archivos, nombres de módulos y a veces valores de
variables. El cliente recibe un mensaje legible y un `id_traza`; la traza
completa va al registro del servidor, donde quien la necesita puede buscarla
por ese mismo identificador.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as ExcepcionHTTP

from mai.dominio.solicitudes import DatosDeSolicitudInvalidos, SolicitudNoEncontrada
from mai.observabilidad.traza import id_traza_actual

logger = logging.getLogger(__name__)

CODIGO_VALIDACION = "VALIDACION_ENTRADA"
CODIGO_CUERPO_MALFORMADO = "CUERPO_MALFORMADO"
CODIGO_NO_ENCONTRADO = "RECURSO_NO_ENCONTRADO"
CODIGO_METODO_NO_PERMITIDO = "METODO_NO_PERMITIDO"
CODIGO_ERROR_INTERNO = "ERROR_INTERNO"

MENSAJE_ERROR_INTERNO = (
    "Ocurrió un error inesperado al procesar la solicitud. "
    "Si el problema persiste, reporte el identificador de traza."
)


def cuerpo_de_error(
    codigo: str, mensaje: str, detalle: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Construye el cuerpo de error. Es el único sitio que define su forma."""
    return {
        "codigo": codigo,
        "mensaje": mensaje,
        "detalle": detalle or {},
        "id_traza": id_traza_actual(),
    }


def respuesta_de_error(
    estado: int, codigo: str, mensaje: str, detalle: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=estado, content=cuerpo_de_error(codigo, mensaje, detalle))


def registrar_manejadores(app: FastAPI) -> None:
    """Conecta los manejadores de error a la aplicación."""

    @app.exception_handler(DatosDeSolicitudInvalidos)
    async def _datos_invalidos(_peticion: Request, error: DatosDeSolicitudInvalidos):
        """422: el cuerpo es JSON válido pero su contenido no sirve.

        Se distingue de 400 a propósito. 400 dice «no pude leer lo que
        enviaste»; 422 dice «lo leí y no cumple». Al cliente le importa la
        diferencia: en el primer caso revisa su serializador, en el segundo
        sus datos.
        """
        return respuesta_de_error(422, CODIGO_VALIDACION, str(error), {"campo": error.campo})

    @app.exception_handler(SolicitudNoEncontrada)
    async def _no_encontrada(_peticion: Request, error: SolicitudNoEncontrada):
        return respuesta_de_error(404, CODIGO_NO_ENCONTRADO, str(error))

    @app.exception_handler(RequestValidationError)
    async def _validacion_de_pydantic(_peticion: Request, error: RequestValidationError):
        """Traduce los errores de pydantic a nuestra forma.

        Sin esta traducción la API tendría dos formas de error: la nuestra y
        la del marco. Es el costo declarado al adoptar la dependencia
        (docs/decisiones.md D-004).

        Un cuerpo que no es JSON llega aquí como error de tipo `json_invalid`
        y se responde 400, no 422: no llegó a haber contenido que validar.
        """
        problemas = error.errors()
        if any(p.get("type") == "json_invalid" for p in problemas):
            return respuesta_de_error(
                400,
                CODIGO_CUERPO_MALFORMADO,
                "El cuerpo de la petición no es JSON válido.",
            )

        campos = {
            ".".join(str(parte) for parte in p.get("loc", ())[1:]): p.get("msg", "")
            for p in problemas
        }
        return respuesta_de_error(
            422,
            CODIGO_VALIDACION,
            "Los datos enviados no cumplen el contrato de la API.",
            {"campos": campos},
        )

    @app.exception_handler(ExcepcionHTTP)
    async def _http(_peticion: Request, error: ExcepcionHTTP):
        """Rutas inexistentes y métodos no permitidos, con la misma forma."""
        codigos = {404: CODIGO_NO_ENCONTRADO, 405: CODIGO_METODO_NO_PERMITIDO}
        return respuesta_de_error(
            error.status_code,
            codigos.get(error.status_code, CODIGO_ERROR_INTERNO),
            str(error.detail),
        )

    @app.exception_handler(Exception)
    async def _no_previsto(_peticion: Request, error: Exception):
        """500: solo lo no previsto.

        La excepción completa va al registro con su traza; al cliente le llega
        un mensaje genérico y el identificador con el que se puede encontrar
        esa traza. Devolver el texto de la excepción filtraría detalles
        internos y, a veces, datos de otros usuarios.
        """
        logger.exception(
            "error_no_previsto",
            extra={"id_traza": id_traza_actual(), "tipo": type(error).__name__},
        )
        return respuesta_de_error(500, CODIGO_ERROR_INTERNO, MENSAJE_ERROR_INTERNO)

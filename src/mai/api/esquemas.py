"""Contrato de entrada y salida de la API.

Estos modelos son la frontera del sistema. Definen qué se acepta y qué se
devuelve, y son también lo que produce el contrato OpenAPI publicado en
`/docs` — por eso llevan descripciones y ejemplos: el contrato se lee, no
solo se cumple.

Los modelos de entrada y los de salida están separados a propósito. Con uno
solo, cualquier campo que el sistema calcula —el código, la fecha, la
clasificación— sería también un campo que el cliente puede enviar, y habría
que recordar ignorarlo en cada ruta.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mai.dominio.solicitudes import (
    LARGO_MAXIMO_ASUNTO,
    LARGO_MAXIMO_DESCRIPCION,
    Solicitud,
)


class SolicitudNueva(BaseModel):
    """Lo que el cliente envía para crear una solicitud.

    Las cotas de largo se declaran aquí **y** se validan en el dominio. No es
    duplicación ociosa: aquí protegen al proceso —un cuerpo de megabytes se
    rechaza antes de construir nada—, y en el dominio protegen la regla, que
    debe seguir valiendo si mañana las solicitudes entran por un lote o por
    una cola en vez de por HTTP.
    """

    asunto: str = Field(
        min_length=1,
        max_length=LARGO_MAXIMO_ASUNTO,
        description="Resumen del problema, en una línea.",
        examples=["No puedo entrar al sistema de nómina"],
    )
    descripcion: str = Field(
        default="",
        max_length=LARGO_MAXIMO_DESCRIPCION,
        description="Detalle en texto libre. Opcional.",
        examples=["Me pide la contraseña y la rechaza desde ayer."],
    )
    area: str = Field(
        min_length=1,
        description="Área responsable. Debe ser una de las 8 del catálogo.",
        examples=["Aplicaciones"],
    )
    solicitante: str = Field(
        min_length=1,
        max_length=LARGO_MAXIMO_ASUNTO,
        description="Quién reporta. No se envía al proveedor de lenguaje.",
        examples=["usuario001@lafortuna.com.co"],
    )
    canal: str | None = Field(
        default=None,
        description="Por dónde llegó. Si se omite, se asume «Formulario».",
        examples=["Correo"],
    )


class SolicitudCreada(BaseModel):
    """Lo que la API devuelve de una solicitud.

    `origen_clasificacion` y `confianza` viajan al cliente a propósito. Una
    categoría puesta por reglas de reserva no es lo mismo que una puesta por
    el modelo, y quien consume la API debe poder distinguirlas: de eso depende
    si la usa directamente o la manda a revisión.
    """

    codigo: str
    asunto: str
    descripcion: str
    area: str
    solicitante: str
    canal: str
    categoria: str
    prioridad: str
    estado: str
    fecha_creacion: datetime
    origen_clasificacion: str = Field(description="«modelo» o «degradado».")
    confianza: str = Field(description="«alta» o «baja».")
    motivo_degradacion: str | None = Field(
        default=None,
        description="Por qué se degradó, si se degradó. Nulo en caso normal.",
    )

    @classmethod
    def desde_dominio(cls, solicitud: Solicitud) -> SolicitudCreada:
        return cls(**vars(solicitud))


class ListadoDeSolicitudes(BaseModel):
    """Una página de resultados, con lo necesario para pedir la siguiente."""

    datos: list[SolicitudCreada]
    total: int = Field(description="Cuántas cumplen el filtro, ignorando la paginación.")
    limite: int
    desplazamiento: int


class Salud(BaseModel):
    """Respuesta de la sonda."""

    estado: str = Field(examples=["ok"])
    proveedor_clasificacion: str = Field(
        description="Cadena de proveedores configurada para clasificar.",
        examples=["falso"],
    )

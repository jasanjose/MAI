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

from mai.dominio.politicas import RespuestaDePolitica
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


class ConsultaDePolitica(BaseModel):
    """Una pregunta en lenguaje natural sobre las políticas internas."""

    pregunta: str = Field(
        min_length=1,
        max_length=LARGO_MAXIMO_ASUNTO,
        description="La consulta, tal como la escribiría un colaborador.",
        examples=["¿con cuánta anticipación debo pedir vacaciones?"],
    )


class RespuestaDeConsulta(BaseModel):
    """La respuesta, o la declaración de que no hay evidencia.

    Abstenerse **no es un error**: es el comportamiento correcto ante una
    pregunta que las políticas no cubren, y por eso llega con 200. Quien
    consuma la API distingue los dos casos por `origen`, no por el código de
    estado.
    """

    respuesta: str
    citas: list[str] = Field(
        description="Documento y sección que respaldan cada afirmación. Vacío si se abstuvo."
    )
    origen: str = Field(description="«modelo» o «abstencion».")
    confianza: str = Field(description="«alta» o «baja».")
    motivo: str | None = Field(
        default=None,
        description=(
            "Por qué se abstuvo, si se abstuvo. Distingue causas que exigen "
            "acciones distintas: sin_evidencia_suficiente, "
            "respuesta_sin_cita_verificable, "
            "cita_fuera_de_los_fragmentos_recuperados, proveedor_no_disponible."
        ),
    )
    fragmentos_consultados: list[str] = Field(
        description="Qué se recuperó antes de responder. Permite auditar la respuesta."
    )
    mejor_puntaje: float = Field(description="Similitud del fragmento más parecido.")

    @classmethod
    def desde_dominio(cls, respuesta: RespuestaDePolitica) -> RespuestaDeConsulta:
        return cls(
            respuesta=respuesta.texto,
            citas=list(respuesta.citas),
            origen=respuesta.origen,
            confianza=respuesta.confianza,
            motivo=respuesta.motivo,
            fragmentos_consultados=list(respuesta.fragmentos_consultados),
            mejor_puntaje=round(respuesta.mejor_puntaje, 4),
        )


class Salud(BaseModel):
    """Respuesta de la sonda."""

    estado: str = Field(examples=["ok"])
    proveedor_clasificacion: str = Field(
        description="Cadena de proveedores configurada para clasificar.",
        examples=["falso"],
    )
    proveedor_rag: str = Field(
        description=(
            "Cadena configurada para responder políticas. Con «falso» toda "
            "consulta se abstendrá en la verificación de cita, porque el "
            "adaptador de pruebas no cita."
        ),
        examples=["openai,dashscope"],
    )
    fragmentos_indexados: int = Field(
        description=(
            "Cuántos fragmentos de política hay cargados. **Cero significa que "
            "toda consulta se va a abstener**: normalmente indica que "
            "MAI_RUTA_POLITICAS no apunta al corpus."
        ),
        examples=[67],
    )

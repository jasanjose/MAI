"""Aplicación HTTP de MAI.

Esta capa hace tres cosas y ninguna más: traducir HTTP a llamadas del
dominio, traducir errores del dominio a códigos de estado, y no dejar pasar
una excepción cruda. **No hay lógica de negocio aquí.** Si aparece una regla
en este archivo, está en el sitio equivocado.

`crear_app` es una fábrica y no una aplicación global por un motivo concreto:
permite construir la aplicación con un proveedor de lenguaje distinto sin
tocar variables de entorno del proceso. Las pruebas lo usan para inyectar el
adaptador falso; producción la construye desde el entorno.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response, status

from mai.adaptadores.llm.fabrica import construir_para_clasificacion
from mai.adaptadores.persistencia.repositorio_memoria import RepositorioEnMemoria
from mai.api.errores import registrar_manejadores
from mai.api.esquemas import ListadoDeSolicitudes, Salud, SolicitudCreada, SolicitudNueva
from mai.dominio.clasificacion import Clasificador
from mai.dominio.puertos import ProveedorLLM
from mai.dominio.solicitudes import (
    LIMITE_MAXIMO,
    LIMITE_POR_DEFECTO,
    FiltrosDeListado,
    RepositorioSolicitudes,
    ServicioSolicitudes,
)
from mai.observabilidad.traza import (
    CABECERA_TRAZA,
    fijar_id_traza,
    id_traza_actual,
    normalizar_id_traza,
)

logger = logging.getLogger(__name__)

TITULO = "MAI · Mesa de Ayuda Inteligente"
VERSION = "0.1.0"
DESCRIPCION = """\
API de la mesa de ayuda. Recibe solicitudes en texto libre, las clasifica
contra un catálogo cerrado de 12 categorías y permite consultarlas.

La clasificación **nunca impide la creación**: si el proveedor de lenguaje no
responde, la solicitud se crea igual con una clasificación por reglas,
marcada con `origen_clasificacion: "degradado"` y `confianza: "baja"`.

Todos los errores tienen la misma forma:
`{codigo, mensaje, detalle, id_traza}`.
"""


def crear_app(
    proveedor: ProveedorLLM | None = None,
    repositorio: RepositorioSolicitudes | None = None,
) -> FastAPI:
    """Construye la aplicación.

    Sin argumentos, arma la cadena de proveedores desde el entorno y usa el
    repositorio en memoria. Con ellos, se compone lo que se le pase — que es
    lo que permite probar la API entera sin red ni credenciales.
    """
    app = FastAPI(title=TITULO, version=VERSION, description=DESCRIPCION)

    proveedor = proveedor if proveedor is not None else construir_para_clasificacion()
    repositorio = repositorio if repositorio is not None else RepositorioEnMemoria()
    servicio = ServicioSolicitudes(repositorio, Clasificador(proveedor))

    app.state.proveedor = proveedor
    app.state.servicio = servicio

    registrar_manejadores(app)
    _registrar_traza(app)
    _registrar_rutas(app)
    return app


def _obtener_servicio(peticion: Request) -> ServicioSolicitudes:
    return peticion.app.state.servicio


ServicioInyectado = Annotated[ServicioSolicitudes, Depends(_obtener_servicio)]


def _registrar_traza(app: FastAPI) -> None:
    @app.middleware("http")
    async def _traza(peticion: Request, siguiente):
        """Fija el identificador de traza y lo devuelve en la respuesta.

        Va en un middleware y no en cada ruta para que ninguna pueda
        olvidarlo — incluidas las respuestas de error, que son justamente
        cuando el identificador hace falta.
        """
        fijar_id_traza(normalizar_id_traza(peticion.headers.get(CABECERA_TRAZA)))
        respuesta: Response = await siguiente(peticion)
        respuesta.headers[CABECERA_TRAZA] = id_traza_actual()
        return respuesta


def _registrar_rutas(app: FastAPI) -> None:
    @app.get("/salud", response_model=Salud, tags=["operación"], summary="Sonda del servicio")
    async def salud(peticion: Request) -> Salud:
        """Indica si el servicio responde y con qué cadena de proveedores.

        Devolver la cadena configurada sirve para diagnosticar el problema
        más frecuente al desplegar: creer que se apuntó a un proveedor real
        y estar corriendo contra el falso.
        """
        proveedor: ProveedorLLM = peticion.app.state.proveedor
        cadena = getattr(proveedor, "proveedores", (proveedor.nombre,))
        return Salud(estado="ok", proveedor_clasificacion=",".join(cadena))

    @app.post(
        "/solicitudes",
        response_model=SolicitudCreada,
        status_code=status.HTTP_201_CREATED,
        tags=["solicitudes"],
        summary="Crea una solicitud",
    )
    async def crear(cuerpo: SolicitudNueva, servicio: ServicioInyectado) -> SolicitudCreada:
        """Crea una solicitud y la clasifica.

        Devuelve 201 con la solicitud creada, incluido el código asignado.
        Responde 422 si algún dato no cumple, y 400 si el cuerpo no es JSON.
        """
        creada = servicio.crear(
            asunto=cuerpo.asunto,
            descripcion=cuerpo.descripcion,
            area=cuerpo.area,
            solicitante=cuerpo.solicitante,
            canal=cuerpo.canal,
        )
        logger.info(
            "solicitud_creada",
            extra={
                "id_traza": id_traza_actual(),
                "codigo": creada.codigo,
                "area": creada.area,
                "categoria": creada.categoria,
                "origen_clasificacion": creada.origen_clasificacion,
            },
        )
        return SolicitudCreada.desde_dominio(creada)

    @app.get(
        "/solicitudes/{codigo}",
        response_model=SolicitudCreada,
        tags=["solicitudes"],
        summary="Consulta el estado de una solicitud",
    )
    async def obtener(codigo: str, servicio: ServicioInyectado) -> SolicitudCreada:
        """Devuelve la solicitud con ese código, o 404 si no existe."""
        return SolicitudCreada.desde_dominio(servicio.obtener(codigo))

    @app.get(
        "/solicitudes",
        response_model=ListadoDeSolicitudes,
        tags=["solicitudes"],
        summary="Lista solicitudes con filtros",
    )
    async def listar(
        servicio: ServicioInyectado,
        area: Annotated[str | None, Query(description="Una de las 8 áreas.")] = None,
        estado: Annotated[str | None, Query(description="Abierto, Cerrado…")] = None,
        categoria: Annotated[str | None, Query(description="Una de las 12.")] = None,
        prioridad: Annotated[str | None, Query(description="Crítica, Alta…")] = None,
        limite: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO)] = LIMITE_POR_DEFECTO,
        desplazamiento: Annotated[int, Query(ge=0)] = 0,
    ) -> ListadoDeSolicitudes:
        """Lista solicitudes, más recientes primero.

        Un filtro con un valor fuera del catálogo responde 422 y no una lista
        vacía: devolver `[]` ante `estado=cerado` haría creer que no hay
        solicitudes cerradas.
        """
        pagina, total = servicio.listar(
            FiltrosDeListado(
                area=area,
                estado=estado,
                categoria=categoria,
                prioridad=prioridad,
                limite=limite,
                desplazamiento=desplazamiento,
            )
        )
        return ListadoDeSolicitudes(
            datos=[SolicitudCreada.desde_dominio(s) for s in pagina],
            total=total,
            limite=limite,
            desplazamiento=desplazamiento,
        )

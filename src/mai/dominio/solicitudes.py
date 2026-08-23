"""Solicitudes de la mesa de ayuda: modelo, puerto de persistencia y servicio.

El servicio orquesta las tres operaciones que expone la API —crear, consultar
y listar— y no sabe **dónde** se guardan las solicitudes ni **quién** las
clasifica. Recibe un `RepositorioSolicitudes` y un `Clasificador`, ambos
abstracciones, y trabaja contra ellas.

Igual que con el proveedor de lenguaje, el puerto y sus errores viven en el
dominio: el servicio necesita capturarlos, y definirlos en el adaptador
invertiría la dependencia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from mai.dominio.catalogos import (
    normalizar_area,
    normalizar_canal,
    normalizar_categoria,
    normalizar_estado,
    normalizar_prioridad,
)
from mai.dominio.clasificacion import Clasificador

ESTADO_INICIAL = "Abierto"
CANAL_POR_DEFECTO = "Formulario"

LARGO_MAXIMO_ASUNTO = 200
LARGO_MAXIMO_DESCRIPCION = 5000

LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 200


class ErrorDeSolicitud(Exception):
    """Base de los fallos del dominio de solicitudes."""


class SolicitudNoEncontrada(ErrorDeSolicitud):
    """No existe una solicitud con ese código."""


class DatosDeSolicitudInvalidos(ErrorDeSolicitud):
    """Los datos recibidos no permiten crear una solicitud.

    Lleva `campo` para que la capa HTTP pueda decir cuál falló sin adivinarlo
    del texto del mensaje.
    """

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


@dataclass(frozen=True)
class Solicitud:
    """Una solicitud de la mesa de ayuda.

    Es inmutable: cambiar el estado produce una solicitud nueva. Con datos
    que van a un repositorio compartido, un objeto mutable permite que quien
    lo consulte lo modifique sin querer y sin que nadie se entere — que es
    exactamente el defecto S2 del módulo heredado, en otra forma.

    `origen_clasificacion` y `confianza` no son adorno: dicen si la categoría
    la puso un modelo o unas reglas de reserva. Sin ellos, una clasificación
    degradada es indistinguible de una buena.
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
    origen_clasificacion: str
    confianza: str
    motivo_degradacion: str | None = None

    def con_estado(self, estado: str) -> Solicitud:
        """Devuelve una copia con otro estado. No modifica la original."""
        return replace(self, estado=estado)


@dataclass(frozen=True)
class FiltrosDeListado:
    """Criterios de búsqueda. Todos opcionales; ausente significa «no filtra»."""

    area: str | None = None
    estado: str | None = None
    categoria: str | None = None
    prioridad: str | None = None
    limite: int = LIMITE_POR_DEFECTO
    desplazamiento: int = 0


class RepositorioSolicitudes(ABC):
    """Contrato de almacenamiento. El dominio no sabe si detrás hay SQL."""

    @abstractmethod
    def siguiente_codigo(self) -> str:
        """Reserva y devuelve un código nuevo, único y no reutilizable."""

    @abstractmethod
    def guardar(self, solicitud: Solicitud) -> None:
        """Persiste una solicitud. Si el código ya existe, la reemplaza."""

    @abstractmethod
    def obtener(self, codigo: str) -> Solicitud:
        """Devuelve la solicitud, o lanza `SolicitudNoEncontrada`."""

    @abstractmethod
    def listar(self, filtros: FiltrosDeListado) -> list[Solicitud]:
        """Devuelve las solicitudes que cumplen los filtros, más recientes primero."""

    @abstractmethod
    def contar(self, filtros: FiltrosDeListado) -> int:
        """Cuántas cumplen los filtros, ignorando límite y desplazamiento.

        Se separa de `listar` porque quien pagina necesita saber cuántas hay
        en total; devolver solo la página deja al consumidor sin forma de
        saber si debe pedir otra.
        """


class ServicioSolicitudes:
    """Casos de uso de solicitudes.

    Depende de dos abstracciones y de ningún detalle de infraestructura.
    """

    def __init__(self, repositorio: RepositorioSolicitudes, clasificador: Clasificador) -> None:
        self._repositorio = repositorio
        self._clasificador = clasificador

    def crear(
        self,
        asunto: str,
        descripcion: str,
        area: str,
        solicitante: str,
        canal: str | None = None,
    ) -> Solicitud:
        """Valida, clasifica y guarda una solicitud nueva.

        La clasificación **nunca impide la creación**. Si el proveedor no
        responde o devuelve algo fuera del catálogo, el clasificador degrada y
        la solicitud se crea igual, marcada con su origen y su confianza.
        Dejar caer el trabajo de un usuario por un fallo nuestro sería
        cambiar un problema de calidad por uno de pérdida de datos.
        """
        asunto = self._texto_obligatorio(asunto, "asunto", LARGO_MAXIMO_ASUNTO)
        descripcion = self._texto_opcional(descripcion, "descripcion", LARGO_MAXIMO_DESCRIPCION)
        area_normalizada = self._area(area)
        solicitante = self._texto_obligatorio(solicitante, "solicitante", LARGO_MAXIMO_ASUNTO)
        canal_normalizado = self._canal(canal)

        # Al clasificador van solo asunto y descripción: nunca el solicitante.
        clasificacion = self._clasificador.clasificar(asunto, descripcion)

        solicitud = Solicitud(
            codigo=self._repositorio.siguiente_codigo(),
            asunto=asunto,
            descripcion=descripcion,
            area=area_normalizada,
            solicitante=solicitante,
            canal=canal_normalizado,
            categoria=clasificacion.categoria,
            prioridad=clasificacion.prioridad,
            estado=ESTADO_INICIAL,
            fecha_creacion=datetime.now(timezone.utc),
            origen_clasificacion=clasificacion.origen,
            confianza=clasificacion.confianza,
            motivo_degradacion=clasificacion.motivo_degradacion,
        )
        self._repositorio.guardar(solicitud)
        return solicitud

    def obtener(self, codigo: str) -> Solicitud:
        """Consulta una solicitud por su código."""
        codigo = (codigo or "").strip()
        if not codigo:
            raise SolicitudNoEncontrada("Se pidió una solicitud sin código.")
        return self._repositorio.obtener(codigo)

    def listar(self, filtros: FiltrosDeListado) -> tuple[list[Solicitud], int]:
        """Lista solicitudes filtradas. Devuelve la página y el total.

        Los valores de los filtros se normalizan contra los catálogos
        cerrados: buscar «abierto» y «ABIERTO» debe dar lo mismo. Un valor
        que no está en el catálogo es un error del cliente, no una búsqueda
        que devuelve vacío — devolver `[]` ante «estado=cerado» haría creer
        que no hay tickets cerrados.
        """
        filtros = self._normalizar_filtros(filtros)
        return self._repositorio.listar(filtros), self._repositorio.contar(filtros)

    # ── Validación ──────────────────────────────────────────────────────────

    @staticmethod
    def _texto_obligatorio(valor: object, campo: str, largo_maximo: int) -> str:
        texto = str(valor or "").strip()
        if not texto:
            raise DatosDeSolicitudInvalidos(f"El campo «{campo}» es obligatorio.", campo)
        if len(texto) > largo_maximo:
            raise DatosDeSolicitudInvalidos(
                f"El campo «{campo}» supera los {largo_maximo} caracteres permitidos.", campo
            )
        return texto

    @staticmethod
    def _texto_opcional(valor: object, campo: str, largo_maximo: int) -> str:
        texto = str(valor or "").strip()
        if len(texto) > largo_maximo:
            raise DatosDeSolicitudInvalidos(
                f"El campo «{campo}» supera los {largo_maximo} caracteres permitidos.", campo
            )
        return texto

    @staticmethod
    def _area(valor: object) -> str:
        normalizada = normalizar_area(valor)
        if not normalizada.es_valido:
            raise DatosDeSolicitudInvalidos(
                "El campo «area» es obligatorio y debe ser un área conocida.", "area"
            )
        return normalizada.valor

    @staticmethod
    def _canal(valor: object) -> str:
        if valor is None or not str(valor).strip():
            return CANAL_POR_DEFECTO
        normalizado = normalizar_canal(valor)
        if not normalizado.es_valido:
            raise DatosDeSolicitudInvalidos(
                "El campo «canal» no corresponde a un canal conocido.", "canal"
            )
        return normalizado.valor

    @staticmethod
    def _normalizar_filtros(filtros: FiltrosDeListado) -> FiltrosDeListado:
        def normalizado(valor: str | None, normalizar, campo: str) -> str | None:
            if valor is None or not str(valor).strip():
                return None
            resultado = normalizar(valor)
            if not resultado.es_valido:
                raise DatosDeSolicitudInvalidos(
                    f"El filtro «{campo}» no corresponde a un valor conocido.", campo
                )
            return resultado.valor

        limite = max(1, min(int(filtros.limite), LIMITE_MAXIMO))
        return FiltrosDeListado(
            area=normalizado(filtros.area, normalizar_area, "area"),
            estado=normalizado(filtros.estado, normalizar_estado, "estado"),
            categoria=normalizado(filtros.categoria, normalizar_categoria, "categoria"),
            prioridad=normalizado(filtros.prioridad, normalizar_prioridad, "prioridad"),
            limite=limite,
            desplazamiento=max(0, int(filtros.desplazamiento)),
        )

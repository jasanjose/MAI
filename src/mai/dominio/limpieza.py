"""Saneamiento del histórico de tickets.

El orden de las operaciones no es casual y es la decisión central de este
módulo: **se normaliza primero y se deduplica después.**

Medido sobre los 2.000 registros: hay 39 identificadores repetidos. En 27 la
fila es idéntica carácter por carácter; en 12 difiere. Pero al mirar qué
difiere en esos 12, resulta que es un espacio sobrante en el `asunto` (los
12) y la caja de la `categoria` (7 de ellos). No son tickets distintos: son
el mismo ticket capturado dos veces con otra escritura.

Deduplicar antes de normalizar produciría 12 conflictos artificiales que
habría que resolver con una regla arbitraria. Normalizar antes los disuelve:
los 39 quedan como duplicados exactos y no hace falta elegir cuál sobrevive.

La regla de conflicto residual existe igual, para los datos que aún no
hemos visto. Ver `resolver_conflicto`.

Nada se descarta en silencio: todo registro que no llega a la salida limpia
va a cuarentena con su motivo (estándar §4).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from mai.dominio.catalogos import (
    normalizar_canal,
    normalizar_categoria,
    normalizar_estado,
    normalizar_prioridad,
)
from mai.dominio.fechas import normalizar_fecha

AREA_AUSENTE = "Sin área"
CATEGORIA_AUSENTE = "Sin clasificar"

MOTIVO_ID_AUSENTE = "id_ausente"
MOTIVO_FECHA_CREACION_AUSENTE = "fecha_creacion_ausente"
MOTIVO_FECHA_CREACION_INVALIDA = "fecha_creacion_invalida"
MOTIVO_FECHA_CIERRE_INVALIDA = "fecha_cierre_invalida"
MOTIVO_CIERRE_ANTES_DE_CREACION = "cierre_anterior_a_creacion"
MOTIVO_ESTADO_AUSENTE = "estado_ausente"
MOTIVO_ESTADO_INVALIDO = "estado_fuera_de_catalogo"
MOTIVO_PRIORIDAD_INVALIDA = "prioridad_fuera_de_catalogo"
MOTIVO_CANAL_INVALIDO = "canal_fuera_de_catalogo"
MOTIVO_CATEGORIA_INVALIDA = "categoria_fuera_de_catalogo"
MOTIVO_REAPERTURAS_INVALIDAS = "reaperturas_no_numericas"
MOTIVO_DUPLICADO_EXACTO = "duplicado_exacto"
MOTIVO_DUPLICADO_EN_CONFLICTO = "duplicado_con_contenido_en_conflicto"


@dataclass(frozen=True)
class TicketLimpio:
    """Un ticket que superó normalización y validación."""

    id: str
    fecha_creacion: date
    fecha_cierre: date | None  # None es válido: el ticket sigue abierto
    area: str
    categoria: str
    prioridad: str
    canal: str
    estado: str
    solicitante: str
    asunto: str
    descripcion: str
    reaperturas: int

    def clave_de_contenido(self) -> tuple:
        """Todo salvo el identificador. Dos tickets con el mismo id y la misma
        clave de contenido son la misma captura repetida."""
        return (
            self.fecha_creacion, self.fecha_cierre, self.area, self.categoria,
            self.prioridad, self.canal, self.estado, self.solicitante,
            self.asunto, self.descripcion, self.reaperturas,
        )


@dataclass(frozen=True)
class RegistroEnCuarentena:
    """Un registro que no llegó a la salida, con por qué y dónde estaba."""

    numero_de_fila: int
    motivo: str
    detalle: str
    fila_original: dict[str, str]


@dataclass
class ReporteCalidad:
    """Lo que hay que poder responder al terminar un proceso por lotes:
    cuántos entraron, cuántos salieron y por qué se cayó cada uno."""

    leidos: int = 0
    limpios: int = 0
    en_cuarentena: int = 0
    motivos: Counter = field(default_factory=Counter)
    valores_por_defecto: Counter = field(default_factory=Counter)

    def como_texto(self) -> str:
        lineas = [
            "REPORTE DE CALIDAD",
            f"  leídos      : {self.leidos}",
            f"  limpios     : {self.limpios}",
            f"  cuarentena  : {self.en_cuarentena}",
        ]
        if self.motivos:
            lineas.append("  motivos de cuarentena:")
            for motivo, cuantos in self.motivos.most_common():
                lineas.append(f"      {cuantos:5d}  {motivo}")
        if self.valores_por_defecto:
            lineas.append("  valores por defecto aplicados:")
            for campo, cuantos in self.valores_por_defecto.most_common():
                lineas.append(f"      {cuantos:5d}  {campo}")
        return "\n".join(lineas)


@dataclass
class ResultadoLimpieza:
    tickets: list[TicketLimpio] = field(default_factory=list)
    cuarentena: list[RegistroEnCuarentena] = field(default_factory=list)
    reporte: ReporteCalidad = field(default_factory=ReporteCalidad)


def limpiar_tickets(filas: list[dict[str, str]]) -> ResultadoLimpieza:
    """Normaliza, valida y deduplica el histórico.

    Recibe las filas crudas tal como salen del CSV. Devuelve los tickets
    limpios, los registros en cuarentena con su motivo, y el reporte de
    calidad. **Ante una lista vacía devuelve un resultado vacío, no falla.**
    """
    resultado = ResultadoLimpieza()
    validos: list[tuple[int, TicketLimpio]] = []

    for numero, fila in enumerate(filas, start=1):
        ticket, motivo, detalle = _validar_fila(fila, resultado.reporte)
        if ticket is None:
            _mandar_a_cuarentena(resultado, numero, motivo, detalle, fila)
        else:
            validos.append((numero, ticket))

    _deduplicar(validos, resultado)
    resultado.reporte.leidos = len(filas)
    resultado.reporte.limpios = len(resultado.tickets)
    resultado.reporte.en_cuarentena = len(resultado.cuarentena)
    return resultado


def _validar_fila(
    fila: dict[str, str], reporte: ReporteCalidad
) -> tuple[TicketLimpio | None, str, str]:
    """Convierte una fila cruda en ticket, o explica por qué no se pudo."""
    identificador = (fila.get("id") or "").strip()
    if not identificador:
        return None, MOTIVO_ID_AUSENTE, "la fila no trae identificador de ticket"

    creacion = normalizar_fecha(fila.get("fecha_creacion"))
    if creacion.esta_vacia:
        return None, MOTIVO_FECHA_CREACION_AUSENTE, "sin fecha de creación"
    if creacion.fue_rechazada:
        return None, MOTIVO_FECHA_CREACION_INVALIDA, str(creacion.motivo_rechazo)

    cierre = normalizar_fecha(fila.get("fecha_cierre"))
    if cierre.fue_rechazada:
        return None, MOTIVO_FECHA_CIERRE_INVALIDA, str(cierre.motivo_rechazo)
    # cierre.esta_vacia es legítimo: son los tickets abiertos.

    if cierre.valor is not None and creacion.valor is not None and cierre.valor < creacion.valor:
        return (
            None,
            MOTIVO_CIERRE_ANTES_DE_CREACION,
            f"cierre {cierre.valor} anterior a creación {creacion.valor}",
        )

    estado = normalizar_estado(fila.get("estado"))
    if estado.esta_vacio:
        return None, MOTIVO_ESTADO_AUSENTE, "sin estado"
    if estado.fue_rechazado:
        return None, MOTIVO_ESTADO_INVALIDO, repr(fila.get("estado"))

    prioridad = normalizar_prioridad(fila.get("prioridad"))
    if prioridad.fue_rechazado:
        return None, MOTIVO_PRIORIDAD_INVALIDA, repr(fila.get("prioridad"))

    canal = normalizar_canal(fila.get("canal"))
    if canal.fue_rechazado:
        return None, MOTIVO_CANAL_INVALIDO, repr(fila.get("canal"))

    categoria = normalizar_categoria(fila.get("categoria"))
    if categoria.fue_rechazado:
        return None, MOTIVO_CATEGORIA_INVALIDA, repr(fila.get("categoria"))

    reaperturas = _normalizar_reaperturas(fila.get("reaperturas"))
    if reaperturas is None:
        return None, MOTIVO_REAPERTURAS_INVALIDAS, repr(fila.get("reaperturas"))

    area = (fila.get("area") or "").strip()
    if not area:
        area = AREA_AUSENTE
        reporte.valores_por_defecto["area → Sin área"] += 1
    if categoria.esta_vacio:
        reporte.valores_por_defecto["categoria → Sin clasificar"] += 1
    if prioridad.esta_vacio:
        reporte.valores_por_defecto["prioridad ausente"] += 1
    if canal.esta_vacio:
        reporte.valores_por_defecto["canal ausente"] += 1

    ticket = TicketLimpio(
        id=identificador,
        fecha_creacion=creacion.valor,  # type: ignore[arg-type]
        fecha_cierre=cierre.valor,
        area=area,
        categoria=categoria.valor or CATEGORIA_AUSENTE,
        prioridad=prioridad.valor or "Sin prioridad",
        canal=canal.valor or "Sin canal",
        estado=estado.valor,  # type: ignore[arg-type]
        solicitante=(fila.get("solicitante") or "").strip(),
        asunto=" ".join((fila.get("asunto") or "").split()),
        descripcion=" ".join((fila.get("descripcion") or "").split()),
        reaperturas=reaperturas,
    )
    return ticket, "", ""


def _normalizar_reaperturas(valor: object) -> int | None:
    """Vacío cuenta como cero: no haber reabierto es un dato, no una ausencia.
    Devuelve None si no es un entero no negativo."""
    texto = str(valor or "").strip()
    if not texto:
        return 0
    try:
        numero = int(texto)
    except ValueError:
        return None
    return numero if numero >= 0 else None


def _deduplicar(validos: list[tuple[int, TicketLimpio]], resultado: ResultadoLimpieza) -> None:
    """Agrupa por identificador y conserva un ticket por cada uno.

    Como la normalización ya corrió, dos capturas del mismo ticket que solo
    diferían en espacios o mayúsculas llegan aquí ya idénticas y se resuelven
    como duplicado exacto, sin necesidad de elegir.
    """
    vistos: dict[str, tuple[int, TicketLimpio]] = {}

    for numero, ticket in validos:
        anterior = vistos.get(ticket.id)
        if anterior is None:
            vistos[ticket.id] = (numero, ticket)
            continue

        _numero_anterior, ticket_anterior = anterior
        if ticket_anterior.clave_de_contenido() == ticket.clave_de_contenido():
            _mandar_a_cuarentena(
                resultado, numero, MOTIVO_DUPLICADO_EXACTO,
                f"repite exactamente al ticket {ticket.id} ya procesado",
                _a_fila(ticket),
            )
            continue

        conservado, descartado = resolver_conflicto(ticket_anterior, ticket)
        vistos[ticket.id] = (numero, conservado)
        _mandar_a_cuarentena(
            resultado, numero, MOTIVO_DUPLICADO_EN_CONFLICTO,
            f"mismo id {ticket.id} con contenido distinto; se conservó la "
            f"captura más completa y esta se aparta para revisión",
            _a_fila(descartado),
        )

    resultado.tickets = [t for _n, t in vistos.values()]


def resolver_conflicto(
    primero: TicketLimpio, segundo: TicketLimpio
) -> tuple[TicketLimpio, TicketLimpio]:
    """Elige qué captura sobrevive cuando dos filas comparten id y difieren
    de verdad, es decir, cuando la diferencia sobrevivió a la normalización.

    Regla: **se conserva la más completa** —la que tiene menos campos vacíos—
    y en caso de empate, la primera que apareció. La descartada **no se
    pierde**: va a cuarentena con su motivo, para que alguien pueda revisarla.

    Se eligió «la más completa» y no «la más reciente» porque el histórico no
    tiene un campo de versión ni de captura: la única noción de «reciente»
    sería la posición en el archivo, que no es un hecho del negocio sino del
    orden en que se exportó.

    En los 2.000 registros del histórico esta función no se ejecuta ni una
    vez, porque normalizar antes disuelve las 12 diferencias aparentes.
    Existe para los datos que todavía no hemos visto.
    """
    if _campos_con_dato(segundo) > _campos_con_dato(primero):
        return segundo, primero
    return primero, segundo


def _campos_con_dato(ticket: TicketLimpio) -> int:
    return sum(
        1
        for valor in (ticket.fecha_cierre, ticket.solicitante, ticket.asunto,
                      ticket.descripcion)
        if valor not in (None, "")
    ) + sum(
        1
        for valor in (ticket.area, ticket.categoria)
        if valor not in (AREA_AUSENTE, CATEGORIA_AUSENTE)
    )


def _mandar_a_cuarentena(
    resultado: ResultadoLimpieza, numero: int, motivo: str, detalle: str, fila: dict[str, str]
) -> None:
    resultado.cuarentena.append(
        RegistroEnCuarentena(
            numero_de_fila=numero, motivo=motivo, detalle=detalle, fila_original=fila
        )
    )
    resultado.reporte.motivos[motivo] += 1


def _a_fila(ticket: TicketLimpio) -> dict[str, str]:
    return {
        "id": ticket.id,
        "fecha_creacion": ticket.fecha_creacion.isoformat(),
        "fecha_cierre": ticket.fecha_cierre.isoformat() if ticket.fecha_cierre else "",
        "area": ticket.area,
        "categoria": ticket.categoria,
        "prioridad": ticket.prioridad,
        "canal": ticket.canal,
        "solicitante": ticket.solicitante,
        "asunto": ticket.asunto,
        "descripcion": ticket.descripcion,
        "estado": ticket.estado,
        "reaperturas": str(ticket.reaperturas),
    }

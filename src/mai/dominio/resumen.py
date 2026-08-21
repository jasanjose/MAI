"""Resumen del histórico saneado, por área y por prioridad."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from mai.dominio.limpieza import TicketLimpio

ESTADOS_ABIERTOS = frozenset({"Abierto", "En proceso", "Reabierto", "Escalado"})
# Orden de negocio, no alfabético: así se lee un informe de prioridades.
ORDEN_PRIORIDAD = ("Crítica", "Alta", "Media", "Baja", "Sin prioridad")

_ENCABEZADO = f"  {'':<20}{'total':>7}{'abiertos':>10}{'cerrados':>10}{'reap.%':>9}"


@dataclass
class FilaResumen:
    """Una línea del resumen, ya sea de un área o de una prioridad."""

    nombre: str
    total: int = 0
    abiertos: int = 0
    cerrados: int = 0
    reaperturas: int = 0
    por_prioridad: Counter = field(default_factory=Counter)

    @property
    def tasa_reapertura(self) -> float:
        """Porcentaje de tickets con al menos una reapertura.

        Devuelve 0.0 cuando no hay tickets: dividir por cero aquí sería el
        defecto clásico de un informe que se rompe con un área sin actividad.
        """
        if self.total == 0:
            return 0.0
        return round(self.reaperturas / self.total * 100, 2)


@dataclass
class Resumen:
    por_area: list[FilaResumen] = field(default_factory=list)
    por_prioridad: list[FilaResumen] = field(default_factory=list)
    total: int = 0

    def como_texto(self) -> str:
        lineas = [f"RESUMEN — {self.total} tickets", "", "Por área:", _ENCABEZADO]
        for fila in self.por_area:
            lineas.append(
                f"  {fila.nombre:<20}{fila.total:>7}{fila.abiertos:>10}"
                f"{fila.cerrados:>10}{fila.tasa_reapertura:>9.2f}"
            )
        lineas += ["", "Por prioridad:", _ENCABEZADO]
        for fila in self.por_prioridad:
            lineas.append(
                f"  {fila.nombre:<20}{fila.total:>7}{fila.abiertos:>10}"
                f"{fila.cerrados:>10}{fila.tasa_reapertura:>9.2f}"
            )
        return "\n".join(lineas)


def resumir(tickets: list[TicketLimpio]) -> Resumen:
    """Agrupa los tickets por área y por prioridad.

    Recibe la lista de tickets ya saneados. Ante una lista vacía devuelve un
    resumen vacío con total 0, sin fallar ni dividir por cero.
    """
    areas: dict[str, FilaResumen] = defaultdict(lambda: FilaResumen(""))
    prioridades: dict[str, FilaResumen] = defaultdict(lambda: FilaResumen(""))

    for ticket in tickets:
        for clave, agrupacion in ((ticket.area, areas), (ticket.prioridad, prioridades)):
            fila = agrupacion[clave]
            fila.nombre = clave
            fila.total += 1
            if ticket.estado in ESTADOS_ABIERTOS:
                fila.abiertos += 1
            else:
                fila.cerrados += 1
            if ticket.reaperturas > 0:
                fila.reaperturas += 1
        areas[ticket.area].por_prioridad[ticket.prioridad] += 1

    return Resumen(
        # Áreas por volumen descendente: lo que más pesa se lee primero.
        por_area=sorted(areas.values(), key=lambda f: (-f.total, f.nombre)),
        # Prioridades en orden de negocio, no alfabético ni por volumen.
        por_prioridad=sorted(
            prioridades.values(),
            key=lambda f: ORDEN_PRIORIDAD.index(f.nombre)
            if f.nombre in ORDEN_PRIORIDAD
            else len(ORDEN_PRIORIDAD),
        ),
        total=len(tickets),
    )

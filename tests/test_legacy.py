"""Pruebas de los tres defectos de `legacy_module.py`.

Cada bloque se escribe **antes** de su arreglo y falla contra el módulo tal
como se recibió. El commit que trae la prueba deja la suite en rojo a
propósito: es lo que separa entender la causa de silenciar el síntoma.

Los tres síntomas están descritos al inicio del módulo heredado. Aquí se
traducen a comportamiento verificable.
"""

from datetime import date

from legacy_module import filtrar_por_periodo, informe_mensual


def _ticket(identificador: str, fecha_creacion: str) -> dict[str, str]:
    """Ticket mínimo con los únicos campos que el filtro mira."""
    return {"id": identificador, "fecha_creacion": fecha_creacion}


# ---------------------------------------------------------------------------
# S1 · «El informe mensual siempre pierde algunos tickets»
#
# El docstring de `filtrar_por_periodo` dice que el periodo incluye ambos
# extremos. Estas pruebas fijan ese contrato.
# ---------------------------------------------------------------------------

INICIO_MARZO = date(2025, 3, 1)
FIN_MARZO = date(2025, 3, 31)


def test_incluye_los_tickets_creados_dentro_del_periodo():
    """Camino normal: lo que cae en medio del periodo entra."""
    tickets = [_ticket("T-1", "2025-03-15")]

    resultado = filtrar_por_periodo(tickets, INICIO_MARZO, FIN_MARZO)

    assert [t["id"] for t in resultado] == ["T-1"]


def test_no_pierde_el_ticket_creado_el_primer_dia_del_periodo():
    """Borde inferior: el contrato dice que `inicio` está incluido."""
    tickets = [_ticket("T-PRIMERO", "2025-03-01")]

    resultado = filtrar_por_periodo(tickets, INICIO_MARZO, FIN_MARZO)

    assert [t["id"] for t in resultado] == ["T-PRIMERO"]


def test_no_pierde_el_ticket_creado_el_ultimo_dia_del_periodo():
    """Borde superior: el contrato dice que `fin` está incluido."""
    tickets = [_ticket("T-ULTIMO", "2025-03-31")]

    resultado = filtrar_por_periodo(tickets, INICIO_MARZO, FIN_MARZO)

    assert [t["id"] for t in resultado] == ["T-ULTIMO"]


def test_excluye_los_tickets_de_fuera_del_periodo():
    """Un día antes y un día después quedan fuera. El filtro sigue filtrando."""
    tickets = [
        _ticket("T-ANTES", "2025-02-28"),
        _ticket("T-DESPUES", "2025-04-01"),
    ]

    resultado = filtrar_por_periodo(tickets, INICIO_MARZO, FIN_MARZO)

    assert resultado == []


def test_el_informe_mensual_cuenta_los_tickets_de_los_extremos():
    """El síntoma tal como lo reportó el área, sobre la función que usan.

    Se comprueba solo `total`, que sale de `len()`. `por_area` depende de
    `resumir_por_area`, que arrastra el defecto S2: mezclarlos haría que
    esta prueba fallara por dos motivos distintos y dejaría de señalar uno.
    """
    tickets = [
        _ticket("T-PRIMERO", "2025-03-01"),
        _ticket("T-MEDIO", "2025-03-15"),
        _ticket("T-ULTIMO", "2025-03-31"),
    ]

    informe = informe_mensual(tickets, 2025, 3)

    assert informe["total"] == 3

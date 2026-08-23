"""Pruebas de los tres defectos de `legacy_module.py`.

Cada bloque se escribe **antes** de su arreglo y falla contra el módulo tal
como se recibió. El commit que trae la prueba deja la suite en rojo a
propósito: es lo que separa entender la causa de silenciar el síntoma.

Los tres síntomas están descritos al inicio del módulo heredado. Aquí se
traducen a comportamiento verificable.
"""

from datetime import date

from legacy_module import (  # noqa: I001
    contar_reaperturas,
    filtrar_por_periodo,
    informe_mensual,
    resumir_por_area,
    tasa_reapertura,
)


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


# ---------------------------------------------------------------------------
# S2 · «Al generar varios resúmenes seguidos, el segundo en adelante sale
#       inflado»
#
# Aviso sobre cómo están escritas estas pruebas, porque la forma obvia NO
# detecta el defecto:
#
#     primero = resumir_por_area(tickets)
#     segundo = resumir_por_area(tickets)
#     assert segundo == primero        # <- pasa aunque el defecto exista
#
# Pasa porque `primero is segundo`: con el argumento mutable, las dos
# llamadas devuelven el MISMO objeto, y esa comparación es un objeto contra
# sí mismo. Por eso aquí se fotografía el resultado con `dict(...)` antes de
# volver a llamar.
# ---------------------------------------------------------------------------

TICKETS_DE_TRES_AREAS = [
    {"area": "TI"},
    {"area": "TI"},
    {"area": "Gestión Humana"},
]


def test_cuenta_los_tickets_por_area():
    """Camino normal.

    Se pasa un acumulador explícito a propósito. El acumulador por defecto es
    compartido por todo el proceso, así que ya viene contaminado por cualquier
    prueba anterior que haya llamado a `informe_mensual`. Pasarlo explícito
    hace que esta prueba mida la lógica de conteo y no el orden de ejecución.
    """
    resultado = resumir_por_area(TICKETS_DE_TRES_AREAS, {})

    assert resultado == {"TI": 2, "Gestión Humana": 1}


def test_dos_resumenes_seguidos_no_inflan_las_cifras():
    """El síntoma que reportó el área, en su forma más directa."""
    primero = dict(resumir_por_area(TICKETS_DE_TRES_AREAS))
    segundo = dict(resumir_por_area(TICKETS_DE_TRES_AREAS))

    assert segundo == primero


def test_cada_llamada_devuelve_un_diccionario_propio():
    """La causa, aislada: dos llamadas no pueden compartir el mismo objeto."""
    primero = resumir_por_area(TICKETS_DE_TRES_AREAS)
    segundo = resumir_por_area(TICKETS_DE_TRES_AREAS)

    assert primero is not segundo


def test_un_resumen_ya_entregado_no_cambia_al_generar_el_siguiente():
    """La consecuencia más difícil de rastrear en producción.

    Quien recibió el primer resumen no volvió a tocarlo, pero sus cifras
    cambian solas cuando alguien más pide otro. Un informe ya impreso y el
    mismo informe consultado después no coinciden, y nada en el código
    sugiere dónde mirar.
    """
    entregado = resumir_por_area(TICKETS_DE_TRES_AREAS)
    total_al_entregarlo = sum(entregado.values())

    resumir_por_area(TICKETS_DE_TRES_AREAS)

    assert sum(entregado.values()) == total_al_entregarlo


def test_el_acumulador_explicito_sigue_acumulando():
    """El parámetro tiene un uso legítimo y el arreglo no debe quitarlo.

    Sumar dos lotes sobre el mismo acumulador es para lo que existe. Lo que
    está mal no es el parámetro: es su valor por defecto.
    """
    acumulador = {}

    resumir_por_area([{"area": "TI"}], acumulador)
    resumir_por_area([{"area": "TI"}], acumulador)

    assert acumulador == {"TI": 2}


# ---------------------------------------------------------------------------
# S3 · «El indicador de reaperturas siempre da por debajo de lo que ve la
#       mesa de ayuda en pantalla»
#
# El histórico trae el estado escrito de tres formas: REABIERTO (197 filas),
# Reabierto (166) y reabierto (165). La comparación exacta reconoce solo la
# tercera: cuenta 165 de 528, el 31 %.
# ---------------------------------------------------------------------------


def test_cuenta_el_ticket_reabierto_en_minuscula():
    """Camino normal: la única forma que el código reconocía."""
    assert contar_reaperturas([{"estado": "reabierto"}]) == 1


def test_cuenta_el_ticket_reabierto_en_mayuscula():
    """`REABIERTO` son 197 filas del histórico, casi el 40 % de los reabiertos."""
    assert contar_reaperturas([{"estado": "REABIERTO"}]) == 1


def test_cuenta_el_ticket_reabierto_capitalizado():
    """`Reabierto` son otras 166 filas."""
    assert contar_reaperturas([{"estado": "Reabierto"}]) == 1


def test_cuenta_el_ticket_reabierto_con_espacios_sobrantes():
    """El histórico trae espacios de más en varios campos de texto."""
    assert contar_reaperturas([{"estado": "  Reabierto  "}]) == 1


def test_no_cuenta_los_estados_que_no_son_reapertura():
    """El indicador sigue discriminando: ampliar no es contar de más."""
    tickets = [
        {"estado": "Abierto"},
        {"estado": "CERRADO"},
        {"estado": "En proceso"},
        {"estado": "Escalado"},
    ]

    assert contar_reaperturas(tickets) == 0


def test_no_falla_con_el_estado_ausente_o_vacio():
    """Caso de borde: el histórico tiene campos vacíos y el módulo los recibe."""
    tickets = [{}, {"estado": None}, {"estado": ""}, {"estado": "   "}]

    assert contar_reaperturas(tickets) == 0


def test_la_tasa_de_reapertura_no_divide_por_cero():
    """Caso de borde: conjunto vacío. Devuelve 0.0, no una excepción."""
    assert tasa_reapertura([]) == 0.0


def test_la_tasa_de_reapertura_refleja_el_conteo_corregido():
    """Dos de cuatro reabiertos, escritos de dos formas distintas: 50 %."""
    tickets = [
        {"estado": "REABIERTO"},
        {"estado": "reabierto"},
        {"estado": "Cerrado"},
        {"estado": "Abierto"},
    ]

    assert tasa_reapertura(tickets) == 50.0


def test_no_cuenta_un_ticket_ya_cerrado_que_tuvo_reaperturas():
    """LIMITE DECLARADO, no un descuido. Fija el comportamiento actual.

    `contar_reaperturas` mira el estado ACTUAL. Un ticket que se reabrió dos
    veces y después se cerró tiene `reaperturas = 2` y `estado = Cerrado`, y
    no se cuenta — aunque el docstring diga «fueron reabiertos al menos una
    vez», que en sentido literal lo incluiría.

    En el histórico son 58 tickets de los 559 con contador mayor que cero.

    No se corrige aquí porque no es un defecto de código sino una pregunta
    para el negocio: ¿el indicador mide «cuántos están reabiertos hoy» o
    «cuántos se reabrieron alguna vez»? Son dos indicadores distintos y el
    módulo no dice cuál pidió el área. Esta prueba deja el comportamiento
    fijado para que cambiarlo sea una decisión y no un efecto secundario.
    """
    tickets = [{"estado": "Cerrado", "reaperturas": "2"}]

    assert contar_reaperturas(tickets) == 0


def test_contar_reaperturas_no_falla_con_un_estado_que_no_es_texto():
    """Regresión introducida por el propio arreglo de S3.

    El código original comparaba `t.get("estado") == "reabierto"`: con un
    entero devolvía False sin romperse. El arreglo añadió `.strip().lower()`,
    que exige texto, y con eso una fila cuyo estado no sea una cadena tumba el
    informe entero en vez de no contarse.

    Desde un CSV el caso no ocurre —`csv.DictReader` siempre entrega
    cadenas—, pero estas funciones son públicas y reciben diccionarios de
    donde sea: JSON, un ORM, otra parte del sistema. Corregir un defecto no
    puede estrechar el contrato de la función.
    """
    tickets = [{"estado": 123}, {"estado": []}, {"estado": {"raro": True}}]

    assert contar_reaperturas(tickets) == 0


def test_la_tasa_de_reapertura_tampoco_falla_con_estados_que_no_son_texto():
    """`tasa_reapertura` llama a `contar_reaperturas`: arrastra el defecto."""
    assert tasa_reapertura([{"estado": 123}, {"estado": "Reabierto"}]) == 50.0

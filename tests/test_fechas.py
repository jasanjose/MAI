"""Pruebas del normalizador de fechas.

Los nombres describen el comportamiento esperado, no la implementación:
si mañana el normalizador se reescribe, estas pruebas siguen valiendo.
"""

from datetime import date

import pytest

from mai.dominio.fechas import (
    MOTIVO_FECHA_INEXISTENTE,
    MOTIVO_FORMATO_NO_RECONOCIDO,
    MOTIVO_MES_NO_RECONOCIDO,
    normalizar_fecha,
)

# ── Camino normal: los tres formatos del histórico ──────────────────────────


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("2025-03-08", date(2025, 3, 8)),
        ("08/03/2025", date(2025, 3, 8)),
        ("08-Mar-2025", date(2025, 3, 8)),
    ],
)
def test_convierte_los_tres_formatos_del_historico(entrada, esperada):
    assert normalizar_fecha(entrada).valor == esperada


@pytest.mark.parametrize(
    ("abreviatura", "mes"),
    [("Ene", 1), ("Feb", 2), ("Mar", 3), ("Abr", 4), ("May", 5), ("Jun", 6),
     ("Jul", 7), ("Ago", 8), ("Sep", 9), ("Oct", 10), ("Nov", 11), ("Dic", 12)],
)
def test_reconoce_los_doce_meses_en_espanol(abreviatura, mes):
    """Sin esto, `%b` fallaría en cualquier entorno con locale distinto de es_ES."""
    resultado = normalizar_fecha(f"15-{abreviatura}-2025")
    assert resultado.valor == date(2025, mes, 15)


@pytest.mark.parametrize("entrada", ["15-ENE-2025", "15-ene-2025", "15-Ene-2025"])
def test_el_mes_en_espanol_no_depende_de_mayusculas(entrada):
    assert normalizar_fecha(entrada).valor == date(2025, 1, 15)


def test_no_confunde_dia_y_mes_en_el_formato_con_barras():
    """03/08 es 3 de agosto, no 8 de marzo. El histórico usa dd/mm/aaaa."""
    assert normalizar_fecha("03/08/2025").valor == date(2025, 8, 3)


# ── Casos de borde ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("entrada", ["", "   ", None])
def test_la_fecha_vacia_no_es_un_error(entrada):
    """1.299 `fecha_cierre` del histórico están vacías: son tickets abiertos.
    Tratarlas como error de calidad rompería el dato."""
    resultado = normalizar_fecha(entrada)
    assert resultado.esta_vacia
    assert not resultado.fue_rechazada


def test_una_fecha_que_no_existe_se_rechaza_con_su_motivo():
    """31/02/2025 tiene forma válida pero no es un día real."""
    resultado = normalizar_fecha("31/02/2025")
    assert not resultado.es_valida
    assert resultado.motivo_rechazo == MOTIVO_FECHA_INEXISTENTE


def test_distingue_el_mes_desconocido_del_formato_desconocido():
    """Dos problemas distintos: un mes mal escrito y un formato que el
    histórico no declaraba. El reporte de calidad los cuenta por separado."""
    assert normalizar_fecha("15-Xyz-2025").motivo_rechazo == MOTIVO_MES_NO_RECONOCIDO
    assert normalizar_fecha("basura").motivo_rechazo == MOTIVO_FORMATO_NO_RECONOCIDO


def test_ningun_rechazo_se_pierde_en_silencio():
    """Todo lo que no se convierte vuelve con un motivo utilizable en cuarentena."""
    for entrada in ["basura", "31/02/2025", "15-Xyz-2025", "2025/13/45", "0000-00-00"]:
        resultado = normalizar_fecha(entrada)
        assert resultado.fue_rechazada
        assert resultado.motivo_rechazo


def test_tolera_espacios_alrededor_y_marca_de_orden_de_bytes():
    """El BOM aparece como primer carácter cuando el CSV se guardó desde Excel."""
    assert normalizar_fecha("  2025-03-08  ").valor == date(2025, 3, 8)
    assert normalizar_fecha("﻿2025-03-08").valor == date(2025, 3, 8)


def test_no_lanza_excepcion_ante_ningun_tipo_de_entrada():
    """El normalizador procesa datos externos: nunca debe reventar el proceso."""
    for entrada in [None, "", 12345, 3.14, [], {}, object()]:
        normalizar_fecha(entrada)  # no debe lanzar

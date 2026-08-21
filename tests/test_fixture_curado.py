"""Prueba de punta a punta sobre el fixture curado.

Existe porque `INSUMOS/` no se versiona: sin este archivo, la integración
continua no tendría datos y el pipeline solo estaría probado por partes.

El fixture no es una muestra representativa del histórico: es un archivo de
tensión. Está construido a mano para que cada caso de borde aparezca al
menos una vez, así que su tasa de cuarentena (35 %) es altísima a propósito
y no dice nada sobre la calidad de los datos reales.
"""

from pathlib import Path

from mai.adaptadores.persistencia.csv_tickets import leer_tickets
from mai.dominio.limpieza import (
    MOTIVO_CATEGORIA_INVALIDA,
    MOTIVO_CIERRE_ANTES_DE_CREACION,
    MOTIVO_DUPLICADO_EN_CONFLICTO,
    MOTIVO_DUPLICADO_EXACTO,
    MOTIVO_ESTADO_AUSENTE,
    MOTIVO_FECHA_CIERRE_INVALIDA,
    MOTIVO_FECHA_CREACION_INVALIDA,
    MOTIVO_ID_AUSENTE,
    MOTIVO_REAPERTURAS_INVALIDAS,
    limpiar_tickets,
)

FIXTURE = Path(__file__).parent / "fixtures" / "tickets_muestra.csv"


def procesar():
    return limpiar_tickets(leer_tickets(FIXTURE))


def test_la_marca_de_orden_de_bytes_no_rompe_la_primera_columna():
    """El fixture se guardó con BOM a propósito, como lo hace Excel."""
    assert FIXTURE.read_bytes()[:3] == b"\xef\xbb\xbf"
    assert leer_tickets(FIXTURE)[0]["id"] == "TK-M001"


def test_el_reporte_cuadra_sobre_el_fixture():
    reporte = procesar().reporte
    assert reporte.leidos == 34
    assert reporte.limpios == 22
    assert reporte.en_cuarentena == 12
    assert reporte.leidos == reporte.limpios + reporte.en_cuarentena


def test_el_fixture_ejercita_los_nueve_motivos_de_cuarentena():
    """Si alguien añade un motivo nuevo y no lo cubre aquí, esta prueba avisa."""
    motivos = procesar().reporte.motivos
    esperados = {
        MOTIVO_FECHA_CREACION_INVALIDA: 3,   # basura, 31/02, mes inexistente
        MOTIVO_DUPLICADO_EXACTO: 2,
        MOTIVO_CIERRE_ANTES_DE_CREACION: 1,
        MOTIVO_FECHA_CIERRE_INVALIDA: 1,
        MOTIVO_ID_AUSENTE: 1,
        MOTIVO_ESTADO_AUSENTE: 1,
        MOTIVO_REAPERTURAS_INVALIDAS: 1,
        MOTIVO_CATEGORIA_INVALIDA: 1,
        MOTIVO_DUPLICADO_EN_CONFLICTO: 1,
    }
    assert dict(motivos) == esperados


def test_los_tres_formatos_de_fecha_llegan_a_la_salida():
    tickets = {t.id: t for t in procesar().tickets}
    assert tickets["TK-M001"].fecha_creacion.isoformat() == "2025-03-08"   # ISO
    assert tickets["TK-M002"].fecha_creacion.isoformat() == "2025-03-08"   # dd/mm/aaaa
    assert tickets["TK-M003"].fecha_creacion.isoformat() == "2025-04-08"   # dd-Mmm-aaaa


def test_los_sinonimos_de_catalogo_quedan_normalizados():
    tickets = {t.id: t for t in procesar().tickets}
    assert tickets["TK-M016"].categoria == "Software"      # «aplicaciones»
    assert tickets["TK-M017"].categoria == "Compras"       # «ORDENES DE COMPRA»
    assert tickets["TK-M018"].categoria == "Red"           # «conectividad»
    assert tickets["TK-M018"].canal == "Formulario"        # «Formulario web»
    assert tickets["TK-M013"].prioridad == "Alta"          # «1-Alta»
    assert tickets["TK-M015"].estado == "Reabierto"        # «REABIERTO»


def test_el_duplicado_que_solo_difiere_en_escritura_no_genera_conflicto():
    """TK-M021 aparece dos veces: «compras» vs «COMPRAS» y un espacio de más.
    Normalizar antes de deduplicar lo convierte en duplicado exacto."""
    resultado = procesar()
    conflictos = [c for c in resultado.cuarentena
                  if c.motivo == MOTIVO_DUPLICADO_EN_CONFLICTO]
    assert [c.fila_original["id"] for c in conflictos] == ["TK-M022"]


def test_ante_conflicto_real_sobrevive_la_captura_mas_completa():
    """TK-M022 sí difiere de verdad tras normalizar: una captura viene sin
    solicitante ni descripción. Gana la que trae los datos."""
    tickets = {t.id: t for t in procesar().tickets}
    assert tickets["TK-M022"].solicitante == "usuario077@lafortuna.com.co"
    assert tickets["TK-M022"].descripcion == "Detalle completo del caso."


def test_los_valores_ausentes_reciben_su_valor_declarado():
    tickets = {t.id: t for t in procesar().tickets}
    assert tickets["TK-M007"].area == "Sin área"
    assert tickets["TK-M008"].categoria == "Sin clasificar"
    assert tickets["TK-M009"].categoria == "Sin clasificar"   # literal, no categoría
    assert tickets["TK-M012"].reaperturas == 0                # vacío cuenta como cero
    assert tickets["TK-M006"].fecha_cierre is None            # ticket abierto


def test_la_coma_y_las_comillas_del_asunto_sobreviven_al_recorrido_completo():
    tickets = {t.id: t for t in procesar().tickets}
    assert tickets["TK-M019"].asunto == 'No enciende, urgente y con "comillas"'
    assert tickets["TK-M019"].estado == "Cerrado"  # las columnas no se corrieron

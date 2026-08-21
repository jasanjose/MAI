"""Pruebas del saneamiento del histórico."""

from datetime import date

from mai.dominio.limpieza import (
    AREA_AUSENTE,
    CATEGORIA_AUSENTE,
    MOTIVO_CIERRE_ANTES_DE_CREACION,
    MOTIVO_DUPLICADO_EN_CONFLICTO,
    MOTIVO_DUPLICADO_EXACTO,
    MOTIVO_ESTADO_AUSENTE,
    MOTIVO_FECHA_CREACION_AUSENTE,
    MOTIVO_FECHA_CREACION_INVALIDA,
    MOTIVO_ID_AUSENTE,
    MOTIVO_REAPERTURAS_INVALIDAS,
    limpiar_tickets,
)


def fila(**cambios):
    """Fila válida por defecto; cada prueba altera solo lo que le interesa."""
    base = {
        "id": "TK-00001", "fecha_creacion": "2025-03-08", "fecha_cierre": "2025-03-10",
        "area": "Aplicaciones", "categoria": "Software", "prioridad": "Alta",
        "canal": "correo", "solicitante": "usuario001@lafortuna.com.co",
        "asunto": "No abre la aplicación", "descripcion": "Falla intermitente.",
        "estado": "Cerrado", "reaperturas": "0",
    }
    base.update(cambios)
    return base


# ── Camino normal ───────────────────────────────────────────────────────────


def test_un_ticket_bien_formado_sale_limpio_y_normalizado():
    resultado = limpiar_tickets([fila(prioridad="1-Alta", canal="Telefono",
                                      categoria="aplicaciones", estado="ABIERTO",
                                      fecha_cierre="")])
    ticket = resultado.tickets[0]
    assert ticket.prioridad == "Alta"
    assert ticket.canal == "Teléfono"
    assert ticket.categoria == "Software"
    assert ticket.estado == "Abierto"
    assert ticket.fecha_creacion == date(2025, 3, 8)
    assert ticket.fecha_cierre is None


def test_el_reporte_de_calidad_siempre_cuadra():
    """Lo que entra tiene que salir por algún lado: limpio o en cuarentena.
    Un registro que no aparece en ninguno se perdió en silencio."""
    filas = [fila(id="TK-1"), fila(id=""), fila(id="TK-3", fecha_creacion="basura"),
             fila(id="TK-4"), fila(id="TK-4")]
    resultado = limpiar_tickets(filas)
    reporte = resultado.reporte
    assert reporte.leidos == len(filas)
    assert reporte.leidos == reporte.limpios + reporte.en_cuarentena


# ── Casos de borde ──────────────────────────────────────────────────────────


def test_la_entrada_vacia_no_revienta():
    resultado = limpiar_tickets([])
    assert resultado.tickets == []
    assert resultado.reporte.leidos == 0
    assert resultado.reporte.limpios == 0


def test_la_fecha_de_cierre_vacia_es_un_ticket_abierto_no_un_error():
    """1.299 registros del histórico están así."""
    resultado = limpiar_tickets([fila(fecha_cierre="", estado="Abierto")])
    assert resultado.cuarentena == []
    assert resultado.tickets[0].fecha_cierre is None


def test_el_area_vacia_recibe_un_valor_declarado_no_un_nulo():
    resultado = limpiar_tickets([fila(area="")])
    assert resultado.tickets[0].area == AREA_AUSENTE
    assert resultado.reporte.valores_por_defecto["area → Sin área"] == 1


def test_la_categoria_vacia_queda_como_sin_clasificar():
    resultado = limpiar_tickets([fila(categoria="")])
    assert resultado.tickets[0].categoria == CATEGORIA_AUSENTE


def test_un_cierre_anterior_a_la_creacion_es_inconsistente():
    resultado = limpiar_tickets([fila(fecha_creacion="2025-03-10",
                                      fecha_cierre="2025-03-08")])
    assert resultado.tickets == []
    assert resultado.cuarentena[0].motivo == MOTIVO_CIERRE_ANTES_DE_CREACION


def test_cada_registro_rechazado_conserva_su_motivo_y_su_fila_original():
    """Sin la fila original, la cuarentena no sirve para corregir nada."""
    resultado = limpiar_tickets([fila(id="", asunto="marca")])
    registro = resultado.cuarentena[0]
    assert registro.motivo == MOTIVO_ID_AUSENTE
    assert registro.fila_original["asunto"] == "marca"
    assert registro.numero_de_fila == 1


def test_los_campos_obligatorios_ausentes_van_a_cuarentena_con_su_motivo():
    casos = [
        (fila(id=""), MOTIVO_ID_AUSENTE),
        (fila(fecha_creacion=""), MOTIVO_FECHA_CREACION_AUSENTE),
        (fila(fecha_creacion="31/02/2025"), MOTIVO_FECHA_CREACION_INVALIDA),
        (fila(estado=""), MOTIVO_ESTADO_AUSENTE),
        (fila(reaperturas="dos"), MOTIVO_REAPERTURAS_INVALIDAS),
        (fila(reaperturas="-1"), MOTIVO_REAPERTURAS_INVALIDAS),
    ]
    for entrada, motivo_esperado in casos:
        resultado = limpiar_tickets([entrada])
        assert resultado.tickets == [], f"no debió pasar: {motivo_esperado}"
        assert resultado.cuarentena[0].motivo == motivo_esperado


def test_reaperturas_vacio_cuenta_como_cero():
    """No haber reabierto es un dato, no una ausencia. 93 registros están así."""
    resultado = limpiar_tickets([fila(reaperturas="")])
    assert resultado.tickets[0].reaperturas == 0


def test_una_fila_a_la_que_le_faltan_columnas_no_tumba_el_proceso():
    resultado = limpiar_tickets([{"id": "TK-9", "fecha_creacion": "2025-01-01"}])
    assert resultado.reporte.leidos == 1
    assert resultado.reporte.limpios + resultado.reporte.en_cuarentena == 1


# ── Deduplicación ───────────────────────────────────────────────────────────


def test_normalizar_antes_de_deduplicar_disuelve_las_diferencias_de_escritura():
    """Es el caso real de los 12 ids del histórico: el mismo ticket capturado
    dos veces, con un espacio de más en el asunto y otra caja en la categoría.
    Si se deduplicara antes de normalizar, esto sería un conflicto artificial."""
    resultado = limpiar_tickets([
        fila(id="TK-500", asunto="Estado de la orden 4471", categoria="compras"),
        fila(id="TK-500", asunto="Estado de la orden 4471 ", categoria="COMPRAS"),
    ])
    assert len(resultado.tickets) == 1
    assert resultado.cuarentena[0].motivo == MOTIVO_DUPLICADO_EXACTO


def test_el_duplicado_exacto_se_descarta_pero_queda_registrado():
    resultado = limpiar_tickets([fila(id="TK-7"), fila(id="TK-7")])
    assert len(resultado.tickets) == 1
    assert resultado.reporte.motivos[MOTIVO_DUPLICADO_EXACTO] == 1


def test_ante_un_conflicto_real_se_conserva_la_captura_mas_completa():
    """Si la diferencia sobrevive a la normalización, entonces sí es un
    conflicto y hay que elegir. Se conserva la fila con más datos."""
    incompleta = fila(id="TK-8", descripcion="", solicitante="", fecha_cierre="")
    completa = fila(id="TK-8", descripcion="Detalle del caso.",
                    solicitante="usuario002@lafortuna.com.co", fecha_cierre="2025-03-11")
    resultado = limpiar_tickets([incompleta, completa])
    assert len(resultado.tickets) == 1
    assert resultado.tickets[0].descripcion == "Detalle del caso."


def test_la_captura_descartada_por_conflicto_va_a_cuarentena_no_se_pierde():
    """Elegir una no autoriza a borrar la otra: alguien tiene que poder revisarla."""
    resultado = limpiar_tickets([
        fila(id="TK-8", descripcion="", solicitante="", fecha_cierre=""),
        fila(id="TK-8", descripcion="Detalle.", solicitante="u@lafortuna.com.co"),
    ])
    apartados = [c for c in resultado.cuarentena if c.motivo == MOTIVO_DUPLICADO_EN_CONFLICTO]
    assert len(apartados) == 1
    assert apartados[0].fila_original["id"] == "TK-8"

"""Pruebas del resumen y del script de línea de comandos."""

import csv
from datetime import date

import pytest

from mai.adaptadores.persistencia.csv_tickets import (
    escribir_cuarentena,
    escribir_tickets,
    leer_tickets,
)
from mai.dominio.limpieza import RegistroEnCuarentena, TicketLimpio
from mai.dominio.resumen import resumir
from mai.limpiar_historico import (
    CODIGO_CALIDAD_INSUFICIENTE,
    CODIGO_ENTRADA_ILEGIBLE,
    CODIGO_OK,
    main,
)

ENCABEZADO = ("id,fecha_creacion,fecha_cierre,area,categoria,prioridad,canal,"
              "solicitante,asunto,descripcion,estado,reaperturas\n")


def ticket(**cambios) -> TicketLimpio:
    base = dict(
        id="TK-1", fecha_creacion=date(2025, 3, 1), fecha_cierre=date(2025, 3, 5),
        area="Aplicaciones", categoria="Software", prioridad="Alta", canal="Correo",
        estado="Cerrado", solicitante="u@lafortuna.com.co", asunto="Asunto",
        descripcion="Descripción", reaperturas=0,
    )
    base.update(cambios)
    return TicketLimpio(**base)


# ── Resumen ─────────────────────────────────────────────────────────────────


def test_el_resumen_de_una_lista_vacia_no_divide_por_cero():
    """Un área sin actividad es el caso que rompe los informes mal escritos."""
    resumen = resumir([])
    assert resumen.total == 0
    assert resumen.por_area == []
    assert "0 tickets" in resumen.como_texto()


def test_agrupa_por_area_y_por_prioridad_a_la_vez():
    resumen = resumir([
        ticket(id="A", area="Compras", prioridad="Alta"),
        ticket(id="B", area="Compras", prioridad="Baja"),
        ticket(id="C", area="Calidad", prioridad="Alta"),
    ])
    assert resumen.total == 3
    assert {f.nombre: f.total for f in resumen.por_area} == {"Compras": 2, "Calidad": 1}
    assert {f.nombre: f.total for f in resumen.por_prioridad} == {"Alta": 2, "Baja": 1}


def test_separa_abiertos_de_cerrados_contando_reabierto_como_abierto():
    """Un ticket reabierto está abierto: es trabajo pendiente, no cerrado."""
    resumen = resumir([
        ticket(id="A", estado="Cerrado"),
        ticket(id="B", estado="Reabierto"),
        ticket(id="C", estado="En proceso"),
        ticket(id="D", estado="Escalado"),
    ])
    fila = resumen.por_area[0]
    assert fila.cerrados == 1
    assert fila.abiertos == 3


def test_la_tasa_de_reapertura_cuenta_tickets_no_reaperturas():
    """Un ticket con 3 reaperturas es un ticket reabierto, no tres."""
    resumen = resumir([
        ticket(id="A", reaperturas=3),
        ticket(id="B", reaperturas=0),
    ])
    assert resumen.por_area[0].tasa_reapertura == 50.0


def test_las_prioridades_salen_en_orden_de_negocio_no_alfabetico():
    resumen = resumir([ticket(id=str(i), prioridad=p) for i, p in
                       enumerate(["Baja", "Crítica", "Media", "Alta"])])
    assert [f.nombre for f in resumen.por_prioridad] == ["Crítica", "Alta", "Media", "Baja"]


# ── Escritura de archivos ───────────────────────────────────────────────────


def test_el_csv_escapa_las_comas_del_asunto(tmp_path):
    """Construir un CSV concatenando comas parte la fila en silencio en cuanto
    un asunto trae una. Es el defecto que aparece en el código a revisar."""
    destino = tmp_path / "salida.csv"
    escribir_tickets(destino, [ticket(asunto='No enciende, urgente y con "comillas"')])
    filas = list(csv.DictReader(destino.open(encoding="utf-8")))
    assert len(filas) == 1
    assert filas[0]["asunto"] == 'No enciende, urgente y con "comillas"'
    assert filas[0]["estado"] == "Cerrado"  # las columnas siguientes no se corrieron


def test_la_cuarentena_conserva_la_fila_original_completa(tmp_path):
    destino = tmp_path / "cuarentena.csv"
    escribir_cuarentena(destino, [
        RegistroEnCuarentena(7, "motivo_x", "detalle", {"id": "TK-9", "asunto": "algo"})
    ])
    filas = list(csv.DictReader(destino.open(encoding="utf-8")))
    assert filas[0]["numero_de_fila"] == "7"
    assert "TK-9" in filas[0]["fila_original"]


def test_lee_el_csv_aunque_traiga_marca_de_orden_de_bytes(tmp_path):
    """Sin utf-8-sig la primera columna se llamaría «﻿id» y no se encontraría."""
    origen = tmp_path / "con_bom.csv"
    origen.write_text("﻿" + ENCABEZADO + "TK-1,2025-01-01,,A,Software,Alta,correo,,x,,Abierto,0\n",
                      encoding="utf-8")
    filas = leer_tickets(origen)
    assert filas[0]["id"] == "TK-1"


def test_leer_un_archivo_que_no_existe_avisa_con_claridad(tmp_path):
    with pytest.raises(FileNotFoundError, match="No se encontró el archivo"):
        leer_tickets(tmp_path / "fantasma.csv")


# ── El script de punta a punta ──────────────────────────────────────────────


def test_el_script_procesa_un_archivo_valido_y_devuelve_cero(tmp_path):
    entrada = tmp_path / "entrada.csv"
    entrada.write_text(
        ENCABEZADO + "TK-1,2025-03-08,2025-03-10,Compras,software,1-Alta,correo,"
        "u@lafortuna.com.co,Asunto,Desc,Cerrado,0\n", encoding="utf-8")
    salida = tmp_path / "salida"
    assert main([str(entrada), "--salida", str(salida)]) == CODIGO_OK
    for nombre in ("tickets_limpios.csv", "cuarentena.csv", "resumen.csv"):
        assert (salida / nombre).exists(), nombre


@pytest.mark.parametrize("contenido", ["", ENCABEZADO])
def test_el_archivo_vacio_no_es_un_fallo(tmp_path, contenido):
    """Cero registros es un resultado válido, no un error."""
    entrada = tmp_path / "vacio.csv"
    entrada.write_text(contenido, encoding="utf-8")
    assert main([str(entrada), "--salida", str(tmp_path / "s")]) == CODIGO_OK


def test_el_archivo_inexistente_devuelve_codigo_de_entrada_ilegible(tmp_path):
    assert main([str(tmp_path / "no_existe.csv")]) == CODIGO_ENTRADA_ILEGIBLE


def test_un_archivo_binario_no_revienta_el_proceso(tmp_path):
    entrada = tmp_path / "binario.csv"
    entrada.write_bytes(bytes(range(256)))
    assert main([str(entrada)]) == CODIGO_ENTRADA_ILEGIBLE


def test_demasiada_cuarentena_hace_fallar_el_proceso(tmp_path):
    """Cuando casi todo se cae, el problema no son los registros: es la fuente.
    El código 2 permite que una tubería automatizada lo detecte."""
    entrada = tmp_path / "malo.csv"
    entrada.write_text(ENCABEZADO + "TK-1,basura,,A,Software,Alta,correo,,x,,Abierto,0\n",
                       encoding="utf-8")
    codigo = main([str(entrada), "--salida", str(tmp_path / "s")])
    assert codigo == CODIGO_CALIDAD_INSUFICIENTE

"""Pruebas del registro estructurado en JSON."""

import io
import json
import logging

import pytest

from mai.observabilidad.registro import (
    MARCA_OMITIDO,
    FormateadorJSON,
    configurar_registro,
)
from mai.observabilidad.traza import fijar_id_traza


@pytest.fixture
def salida():
    """Un registro configurado que escribe a memoria en vez de a la consola."""
    destino = io.StringIO()
    configurar_registro(nivel="DEBUG", salida=destino)
    yield destino
    logging.getLogger().handlers.clear()


def lineas(salida) -> list[dict]:
    return [json.loads(linea) for linea in salida.getvalue().splitlines() if linea.strip()]


def test_cada_evento_es_una_linea_json_valida(salida):
    logging.getLogger("prueba").info("algo_paso")

    assert len(lineas(salida)) == 1


def test_el_evento_lleva_nivel_momento_y_modulo(salida):
    logging.getLogger("mi.modulo").warning("cuidado")

    evento = lineas(salida)[0]
    assert evento["nivel"] == "WARNING"
    assert evento["evento"] == "cuidado"
    assert evento["modulo"] == "mi.modulo"
    assert evento["momento"]


def test_los_campos_de_extra_viajan_al_json(salida):
    logging.getLogger("prueba").info(
        "llamada_llm", extra={"proveedor": "groq", "latencia_ms": 42.5}
    )

    evento = lineas(salida)[0]
    assert evento["proveedor"] == "groq"
    assert evento["latencia_ms"] == 42.5


def test_el_id_de_traza_se_incorpora_solo(salida):
    """Que dependa de la memoria de quien escribe el código es garantizar que
    falte justo en el evento que importa."""
    fijar_id_traza("traza-de-la-peticion")

    logging.getLogger("prueba").info("evento_dentro_de_una_peticion")

    assert lineas(salida)[0]["id_traza"] == "traza-de-la-peticion"


def test_sin_traza_activa_el_campo_no_aparece(salida):
    fijar_id_traza("")

    logging.getLogger("prueba").info("evento_fuera_de_peticion")

    assert "id_traza" not in lineas(salida)[0]


# ── Lo que nunca debe salir en un registro ──────────────────────────────────


def test_no_registra_datos_personales_ni_contenido_del_ticket(salida):
    """Un sistema de registro es una copia de los datos con menos controles
    de acceso, y suele conservarse más tiempo."""
    logging.getLogger("prueba").info(
        "solicitud_creada",
        extra={
            "codigo": "SOL-000001",
            "asunto": "No puedo entrar",
            "descripcion": "detalle largo",
            "solicitante": "usuario001@lafortuna.com.co",
        },
    )

    evento = lineas(salida)[0]
    assert evento["codigo"] == "SOL-000001"
    for campo in ("asunto", "descripcion", "solicitante"):
        assert evento[campo] == MARCA_OMITIDO


def test_el_correo_no_aparece_en_ninguna_parte_de_la_linea(salida):
    logging.getLogger("prueba").info(
        "solicitud_creada", extra={"solicitante": "ana.perez@lafortuna.com"}
    )

    assert "ana.perez@lafortuna.com" not in salida.getvalue()


def test_una_excepcion_se_registra_sin_su_traza(salida):
    """La traza completa puede arrastrar valores de variables locales."""
    try:
        raise ValueError("algo con un dato dentro")
    except ValueError:
        logging.getLogger("prueba").exception("error_no_previsto")

    evento = lineas(salida)[0]
    assert evento["excepcion"]["tipo"] == "ValueError"
    assert "Traceback" not in salida.getvalue()


# ── Robustez del propio registro ────────────────────────────────────────────


def test_un_valor_no_serializable_no_tumba_la_linea(salida):
    """Perder una línea por un tipo raro sería cambiar un problema de formato
    por uno de ceguera."""
    from datetime import datetime

    logging.getLogger("prueba").info("evento", extra={"cuando": datetime(2026, 8, 23)})

    assert len(lineas(salida)) == 1


def test_configurar_dos_veces_no_duplica_las_lineas():
    """Sin la guarda, cada línea saldría dos veces: un defecto difícil de
    rastrear porque el contenido es correcto."""
    destino = io.StringIO()
    configurar_registro(nivel="INFO", salida=destino)
    configurar_registro(nivel="INFO", salida=destino)

    logging.getLogger("prueba").info("una_sola_vez")
    logging.getLogger().handlers.clear()

    assert len(lineas(destino)) == 1


def test_el_nivel_filtra_lo_que_no_llega(salida_no_usada=None):
    destino = io.StringIO()
    configurar_registro(nivel="WARNING", salida=destino)

    logging.getLogger("prueba").debug("no deberia salir")
    logging.getLogger("prueba").error("si deberia salir")
    logging.getLogger().handlers.clear()

    eventos = lineas(destino)
    assert len(eventos) == 1
    assert eventos[0]["nivel"] == "ERROR"


def test_el_formateador_produce_json_aunque_el_mensaje_lleve_comillas():
    formateador = FormateadorJSON()
    registro = logging.LogRecord(
        "prueba", logging.INFO, "ruta", 1, 'con "comillas" y \\ barras', None, None
    )

    assert json.loads(formateador.format(registro))["evento"]

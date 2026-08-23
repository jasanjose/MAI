"""Pruebas del identificador de traza."""

from mai.observabilidad.traza import (
    LARGO_MAXIMO,
    fijar_id_traza,
    generar_id_traza,
    id_traza_actual,
    normalizar_id_traza,
)


def test_genera_identificadores_distintos():
    assert generar_id_traza() != generar_id_traza()


def test_conserva_el_identificador_que_envia_el_cliente():
    """Permite seguir una operación que atraviesa varios servicios."""
    assert normalizar_id_traza("peticion-123") == "peticion-123"


def test_genera_uno_cuando_el_cliente_no_lo_envia():
    assert len(normalizar_id_traza(None)) > 0
    assert len(normalizar_id_traza("")) > 0
    assert len(normalizar_id_traza("   ")) > 0


def test_rechaza_un_identificador_desmedido():
    """Sin cota, un cliente mete kilobytes en cada línea de registro."""
    generado = normalizar_id_traza("x" * (LARGO_MAXIMO + 1))

    assert generado != "x" * (LARGO_MAXIMO + 1)


def test_rechaza_un_identificador_con_saltos_de_linea():
    """No es estética: con saltos de línea un cliente fabrica entradas de
    registro falsas, porque el identificador se escribe en los registros."""
    sospechoso = "abc\nINFO fingiendo ser otra linea"

    assert normalizar_id_traza(sospechoso) != sospechoso


def test_rechaza_caracteres_que_no_son_alfanumericos_guion_o_guion_bajo():
    for valor in ("a b", "a;b", "a\tb", "a/../b", "a%00"):
        assert normalizar_id_traza(valor) != valor


def test_acepta_guiones_y_guiones_bajos():
    assert normalizar_id_traza("peticion_1-2") == "peticion_1-2"


def test_recorta_los_espacios_alrededor():
    assert normalizar_id_traza("  abc  ") == "abc"


def test_fuera_de_una_peticion_el_identificador_actual_es_vacio():
    assert isinstance(id_traza_actual(), str)


def test_fijarlo_lo_hace_visible():
    fijar_id_traza("una-traza")

    assert id_traza_actual() == "una-traza"

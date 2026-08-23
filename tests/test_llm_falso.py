"""Pruebas del proveedor de lenguaje falso.

Merecen existir aunque el adaptador sea de pruebas: toda la suite se apoya en
él. Si el falso se comporta distinto de lo que promete, las pruebas que lo
usan dejan de significar lo que dicen significar.
"""

import pytest

from mai.adaptadores.llm.falso import MODELO_FALSO, RESPUESTA_POR_DEFECTO, AdaptadorFalso
from mai.dominio.puertos import ProveedorLLM, ProveedorNoDisponible


def test_cumple_el_contrato_del_puerto():
    """Si deja de implementar `ProveedorLLM`, el desacoplamiento es ficción."""
    assert isinstance(AdaptadorFalso(), ProveedorLLM)


def test_devuelve_la_respuesta_que_se_le_dio():
    proveedor = AdaptadorFalso(["hola"])

    assert proveedor.completar("instrucción", "entrada").texto == "hola"


def test_es_determinista_ante_la_misma_entrada():
    """La razón de existir del adaptador: mismo resultado en cada ejecución."""
    primero = AdaptadorFalso(["fijo"]).completar("i", "e").texto
    segundo = AdaptadorFalso(["fijo"]).completar("i", "e").texto

    assert primero == segundo == "fijo"


def test_sin_respuestas_configuradas_devuelve_la_de_por_defecto():
    assert AdaptadorFalso().completar("i", "e").texto == RESPUESTA_POR_DEFECTO


def test_entrega_las_respuestas_en_orden():
    proveedor = AdaptadorFalso(["primera", "segunda"])

    assert proveedor.completar("i", "e").texto == "primera"
    assert proveedor.completar("i", "e").texto == "segunda"


def test_repite_la_ultima_cuando_se_acaban():
    """Un proveedor no deja de responder porque se acaben las respuestas
    preparadas: eso convertiría un detalle del banco de pruebas en un fallo."""
    proveedor = AdaptadorFalso(["única"])

    assert proveedor.completar("i", "e").texto == "única"
    assert proveedor.completar("i", "e").texto == "única"


def test_registra_cada_llamada_con_sus_dos_canales():
    """`llamadas` es lo que permite verificar que el texto del usuario no se
    coló en la instrucción. Sin ese registro esa prueba no se puede escribir."""
    proveedor = AdaptadorFalso()

    proveedor.completar("soy la instrucción", "soy la entrada")

    assert proveedor.llamadas == [("soy la instrucción", "soy la entrada")]


def test_reporta_el_modelo_y_el_proveedor():
    respuesta = AdaptadorFalso(nombre="falso-rag").completar("i", "e")

    assert respuesta.proveedor == "falso-rag"
    assert respuesta.modelo == MODELO_FALSO


def test_declara_los_tokens_ausentes_en_vez_de_fingir_cero():
    """Un cero se suma en los agregados y ensucia el costo estimado.
    Un None se ve y se excluye."""
    respuesta = AdaptadorFalso().completar("i", "e")

    assert respuesta.tokens_entrada is None
    assert respuesta.tokens_salida is None


# ── La capacidad de fallar, que es lo que permite probar el degradado ───────


def test_falla_siempre_cuando_asi_se_configura():
    proveedor = AdaptadorFalso(falla_siempre=True)

    with pytest.raises(ProveedorNoDisponible):
        proveedor.completar("i", "e")


def test_falla_las_primeras_llamadas_y_despues_responde():
    """Sirve para probar el reintento y la cadena de reserva."""
    proveedor = AdaptadorFalso(["al fin"], fallos_iniciales=2)

    with pytest.raises(ProveedorNoDisponible):
        proveedor.completar("i", "e")
    with pytest.raises(ProveedorNoDisponible):
        proveedor.completar("i", "e")

    assert proveedor.completar("i", "e").texto == "al fin"


def test_el_error_lleva_un_mensaje_legible_y_no_una_traza():
    """Estándar §3: nunca una excepción cruda hacia quien consume."""
    proveedor = AdaptadorFalso(falla_siempre=True, nombre="groq")

    with pytest.raises(ProveedorNoDisponible) as error:
        proveedor.completar("i", "e")

    assert "groq" in str(error.value)
    assert "Intente más tarde" in str(error.value)


def test_registra_tambien_las_llamadas_que_fallan():
    """Una llamada fallida ocurrió: contarla es parte de medir."""
    proveedor = AdaptadorFalso(falla_siempre=True)

    with pytest.raises(ProveedorNoDisponible):
        proveedor.completar("i", "e")

    assert len(proveedor.llamadas) == 1


def test_un_numero_negativo_de_fallos_se_trata_como_cero():
    """Caso de borde: no debe volverse una condición imposible de satisfacer."""
    proveedor = AdaptadorFalso(["ok"], fallos_iniciales=-3)

    assert proveedor.completar("i", "e").texto == "ok"

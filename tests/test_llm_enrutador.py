"""Pruebas de la cadena de proveedores con reserva."""

import json

import pytest

from mai.adaptadores.llm.enrutador import EnrutadorLLM
from mai.adaptadores.llm.falso import AdaptadorFalso
from mai.dominio.clasificacion import MOTIVO_PROVEEDOR_CAIDO, ORIGEN_DEGRADADO, Clasificador
from mai.dominio.puertos import CadenaAgotada, ProveedorLLM


def test_la_cadena_cumple_el_contrato_del_puerto():
    """La decisión central del enrutador: el dominio no distingue un
    proveedor de una cadena de cinco."""
    assert isinstance(EnrutadorLLM([AdaptadorFalso()]), ProveedorLLM)


def test_usa_el_primero_cuando_responde():
    primero = AdaptadorFalso(["del primero"], nombre="primero")
    segundo = AdaptadorFalso(["del segundo"], nombre="segundo")

    respuesta = EnrutadorLLM([primero, segundo]).completar("i", "e")

    assert respuesta.texto == "del primero"
    assert respuesta.proveedor == "primero"
    assert segundo.llamadas == []


def test_cae_al_siguiente_cuando_el_primero_falla():
    primero = AdaptadorFalso(falla_siempre=True, nombre="primero")
    segundo = AdaptadorFalso(["del segundo"], nombre="segundo")

    respuesta = EnrutadorLLM([primero, segundo]).completar("i", "e")

    assert respuesta.texto == "del segundo"
    assert respuesta.proveedor == "segundo"


def test_recorre_toda_la_cadena_hasta_encontrar_uno_que_responda():
    cadena = [
        AdaptadorFalso(falla_siempre=True, nombre="uno"),
        AdaptadorFalso(falla_siempre=True, nombre="dos"),
        AdaptadorFalso(["por fin"], nombre="tres"),
    ]

    respuesta = EnrutadorLLM(cadena).completar("i", "e")

    assert respuesta.proveedor == "tres"


def test_lanza_cadena_agotada_cuando_ninguno_responde():
    cadena = [
        AdaptadorFalso(falla_siempre=True, nombre="uno"),
        AdaptadorFalso(falla_siempre=True, nombre="dos"),
    ]

    with pytest.raises(CadenaAgotada) as error:
        EnrutadorLLM(cadena).completar("i", "e")

    assert "uno" in str(error.value)
    assert "dos" in str(error.value)


def test_el_error_final_conserva_el_motivo_de_cada_eslabon():
    """Sin los motivos, «todo falló» no dice si fue la red, la credencial o
    el modelo — y cada causa exige una acción distinta."""
    cadena = [
        AdaptadorFalso(falla_siempre=True, nombre="groq"),
        AdaptadorFalso(falla_siempre=True, nombre="dashscope"),
    ]

    with pytest.raises(CadenaAgotada) as error:
        EnrutadorLLM(cadena).completar("i", "e")

    assert str(error.value).count("no respondió") >= 2


def test_pasa_la_instruccion_y_la_entrada_sin_alterarlas():
    """El enrutador transporta; no reescribe. Si tocara el prompt, la
    respuesta dependería de qué eslabón atendió."""
    primero = AdaptadorFalso(falla_siempre=True, nombre="primero")
    segundo = AdaptadorFalso(nombre="segundo")

    EnrutadorLLM([primero, segundo]).completar("la instrucción", "la entrada")

    assert segundo.llamadas == [("la instrucción", "la entrada")]


def test_expone_los_eslabones_en_orden():
    cadena = EnrutadorLLM(
        [AdaptadorFalso(nombre="groq"), AdaptadorFalso(nombre="openai")]
    )

    assert cadena.proveedores == ("groq", "openai")


def test_rechaza_una_cadena_vacia():
    """Falla al construir, con un mensaje que dice qué variable revisar."""
    with pytest.raises(ValueError, match="RUTA_CLASIFICACION"):
        EnrutadorLLM([])


# ── Cierre de recursos ──────────────────────────────────────────────────────


class ProveedorQueFallaAlCerrar(AdaptadorFalso):
    def cerrar(self) -> None:
        raise RuntimeError("no pude cerrar")


def test_cierra_todos_los_eslabones_aunque_uno_falle_al_cerrar():
    """Un error cerrando el primero no puede dejar los demás abiertos."""
    cerrados = []

    class ProveedorQueRegistra(AdaptadorFalso):
        def cerrar(self) -> None:
            cerrados.append(self.nombre)

    cadena = EnrutadorLLM(
        [
            ProveedorQueFallaAlCerrar(nombre="rompe"),
            ProveedorQueRegistra(nombre="segundo"),
        ]
    )

    cadena.cerrar()

    assert cerrados == ["segundo"]


def test_funciona_como_gestor_de_contexto():
    with EnrutadorLLM([AdaptadorFalso(["ok"])]) as cadena:
        assert cadena.completar("i", "e").texto == "ok"


# ── Integración con el dominio ──────────────────────────────────────────────


def test_el_clasificador_no_distingue_una_cadena_de_un_proveedor():
    """La prueba del desacoplamiento: se le cambia un proveedor por una
    cadena de tres y el Clasificador no cambia ni se entera."""
    cadena = EnrutadorLLM(
        [
            AdaptadorFalso(falla_siempre=True, nombre="groq"),
            AdaptadorFalso(
                [json.dumps({"categoria": "Red", "prioridad": "Alta"})], nombre="openai"
            ),
        ]
    )

    resultado = Clasificador(cadena).clasificar("No hay internet")

    assert resultado.categoria == "Red"
    assert resultado.proveedor == "openai"
    assert resultado.origen == "modelo"


def test_la_cadena_agotada_activa_el_modo_degradado_del_dominio():
    """El enrutador dice «todos fallaron»; el dominio decide qué significa.

    El adaptador falso NO entra como último eslabón: devolvería un texto que
    parece real justo en el peor momento.
    """
    cadena = EnrutadorLLM(
        [
            AdaptadorFalso(falla_siempre=True, nombre="groq"),
            AdaptadorFalso(falla_siempre=True, nombre="dashscope"),
        ]
    )

    resultado = Clasificador(cadena).clasificar("Olvidé mi contraseña")

    assert resultado.origen == ORIGEN_DEGRADADO
    assert resultado.motivo_degradacion == MOTIVO_PROVEEDOR_CAIDO
    assert resultado.categoria == "Accesos"
    assert resultado.confianza == "baja"

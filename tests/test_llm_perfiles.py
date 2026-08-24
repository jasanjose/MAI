"""Pruebas de los perfiles por proveedor y de su efecto en la petición.

La regla que gobierna este archivo: **se comprueba el efecto, no el campo.**
Verificar que el diccionario contiene `enable_thinking: False` da verde con la
versión rota, porque el defecto no es que no se envíe — es que el proveedor al
que se le envía no mira esa palabra.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from mai.adaptadores.llm.compatible import AdaptadorCompatible
from mai.adaptadores.llm.fabrica import construir_cadena
from mai.adaptadores.llm.perfiles import PERFILES, PerfilProveedor, perfil_de

CLAVE_DE_PRUEBA = "clave-de-prueba"  # noqa: S105  # relleno, no abre nada


def _respuesta(cuerpo: dict) -> httpx.Response:
    return httpx.Response(200, json=cuerpo)


def _captura(cuerpo_respuesta: dict):
    """Transporte que guarda el cuerpo enviado y devuelve lo que se le diga."""

    def manejador(peticion: httpx.Request) -> httpx.Response:
        manejador.enviado = json.loads(peticion.content)
        return _respuesta(cuerpo_respuesta)

    manejador.enviado = None
    return manejador


OK = {"choices": [{"message": {"content": "Hardware"}}]}


# ── La tabla ────────────────────────────────────────────────────────────────


def test_un_proveedor_sin_ajustes_no_anade_nada_a_la_peticion():
    assert perfil_de("groq").cuerpo_extra() == {}


def test_el_nombre_se_normaliza_para_que_la_ruta_admita_mayusculas():
    assert perfil_de("  OpenRouter ") is perfil_de("openrouter")


def test_un_proveedor_que_no_esta_en_la_tabla_devuelve_none():
    assert perfil_de("no-existe-este-proveedor") is None


def test_mutar_lo_devuelto_no_contamina_las_llamadas_siguientes():
    """Es el defecto S2 del módulo heredado, en otro disfraz.

    Si `cuerpo_extra()` devolviera la tabla en vez de una copia, quien mutara
    el diccionario —o algo anidado dentro— cambiaría la configuración de todo
    el proceso, y el síntoma aparecería lejos de la causa.
    """
    primero = perfil_de("openrouter").cuerpo_extra()
    primero["reasoning"]["enabled"] = True
    primero["inventado"] = 1

    assert perfil_de("openrouter").cuerpo_extra() == {"reasoning": {"enabled": False}}


# ── El efecto en la petición ────────────────────────────────────────────────


def test_el_cuerpo_extra_viaja_en_la_peticion():
    manejador = _captura(OK)
    AdaptadorCompatible(
        nombre="p", base_url="https://x.test/v1", api_key=CLAVE_DE_PRUEBA, modelo="m",
        transporte=httpx.MockTransport(manejador), cuerpo_extra={"enable_thinking": False},
    ).completar("instruccion", "entrada")

    assert manejador.enviado["enable_thinking"] is False


def test_sin_cuerpo_extra_la_peticion_sale_igual_que_antes():
    """El parámetro es opcional y su ausencia no cambia una coma.

    Es lo que permite añadirlo sin revisar los cinco proveedores existentes.
    """
    manejador = _captura(OK)
    AdaptadorCompatible(
        nombre="p", base_url="https://x.test/v1", api_key=CLAVE_DE_PRUEBA, modelo="m",
        transporte=httpx.MockTransport(manejador),
    ).completar("instruccion", "entrada")

    assert set(manejador.enviado) == {"model", "temperature", "messages"}


def test_un_perfil_mal_escrito_no_puede_secuestrar_el_modelo_ni_los_mensajes():
    """Degradar la petición es aceptable; cambiar a qué modelo se pregunta, no."""
    manejador = _captura(OK)
    AdaptadorCompatible(
        nombre="p", base_url="https://x.test/v1", api_key=CLAVE_DE_PRUEBA, modelo="el-bueno",
        transporte=httpx.MockTransport(manejador),
        cuerpo_extra={"model": "el-malo", "messages": []},
    ).completar("instruccion", "entrada")

    assert manejador.enviado["model"] == "el-bueno"
    assert len(manejador.enviado["messages"]) == 2


# ── Cada proveedor recibe SU flag, no el del vecino ─────────────────────────


@pytest.mark.parametrize(
    ("proveedor", "clave_propia", "clave_ajena"),
    [
        ("dashscope", "enable_thinking", "reasoning"),
        ("openrouter", "reasoning", "enable_thinking"),
    ],
)
def test_el_flag_de_razonamiento_no_se_cruza_entre_proveedores(
    proveedor, clave_propia, clave_ajena
):
    """El nombre equivocado se ignora en silencio: responde bien, tarde y caro.

    La petición no falla y el proveedor no avisa; simplemente razona cuando no
    debía, y eso se paga en latencia y en tokens de salida. Por eso hace falta
    una prueba y no una revisión: no hay nada que revisar a ojo.
    """
    extra = perfil_de(proveedor).cuerpo_extra()

    assert clave_propia in extra
    assert clave_ajena not in extra


def test_la_fabrica_le_pasa_su_perfil_a_cada_proveedor_de_la_cadena():
    manejador = _captura(OK)
    entorno = {
        "DASHSCOPE_BASE_URL": "https://ds.test/v1",
        "DASHSCOPE_API_KEY": CLAVE_DE_PRUEBA,
        "DASHSCOPE_MODEL": "qwen",
    }
    cadena = construir_cadena("dashscope", entorno=entorno)
    cadena._proveedores[0]._cliente = httpx.Client(
        base_url="https://ds.test/v1", transport=httpx.MockTransport(manejador)
    )
    cadena.completar("instruccion", "entrada")

    assert manejador.enviado["enable_thinking"] is False


# ── Tokens de razonamiento: se leen, y ausentes son None ────────────────────


def test_lee_los_tokens_de_razonamiento_cuando_el_proveedor_los_informa():
    cuerpo = dict(OK)
    cuerpo["usage"] = {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "completion_tokens_details": {"reasoning_tokens": 33},
    }
    r = AdaptadorCompatible(
        nombre="p", base_url="https://x.test/v1", api_key=CLAVE_DE_PRUEBA, modelo="m",
        transporte=httpx.MockTransport(_captura(cuerpo)),
    ).completar("instruccion", "entrada")

    assert r.tokens_razonamiento == 33
    assert r.tokens_salida == 40  # el desglose NO se suma: ya está dentro


def test_sin_desglose_el_razonamiento_es_none_y_no_cero():
    """Cero afirmaría que no razonó. Lo que se sabe es que no lo informó."""
    cuerpo = dict(OK)
    cuerpo["usage"] = {"prompt_tokens": 100, "completion_tokens": 40}
    r = AdaptadorCompatible(
        nombre="p", base_url="https://x.test/v1", api_key=CLAVE_DE_PRUEBA, modelo="m",
        transporte=httpx.MockTransport(_captura(cuerpo)),
    ).completar("instruccion", "entrada")

    assert r.tokens_razonamiento is None


# ── Coherencia ──────────────────────────────────────────────────────────────


def test_todo_perfil_esta_documentado_en_env_example():
    ejemplo = (Path(__file__).parent.parent / ".env.example").read_text(encoding="utf-8")
    documentados = {p.lower() for p in re.findall(r"^([A-Z]+)_BASE_URL", ejemplo, re.M)}

    assert set(PERFILES) == documentados


def test_todo_perfil_declara_su_prefijo_de_entorno():
    for nombre, perfil in PERFILES.items():
        assert isinstance(perfil, PerfilProveedor)
        assert perfil.prefijo_entorno.isupper(), nombre

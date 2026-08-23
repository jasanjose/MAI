"""Pruebas de la construcción de cadenas desde el entorno.

El entorno se pasa como diccionario: ninguna prueba toca `os.environ` ni
depende de cómo esté configurada la máquina donde corre.
"""

import pytest

from mai.adaptadores.llm.compatible import AdaptadorCompatible
from mai.adaptadores.llm.enrutador import EnrutadorLLM
from mai.adaptadores.llm.fabrica import (
    ConfiguracionInvalida,
    construir_cadena,
    construir_para_clasificacion,
    construir_para_rag,
)
from mai.adaptadores.llm.falso import AdaptadorFalso
from mai.dominio.clasificacion import Clasificador
from mai.dominio.puertos import ProveedorLLM

ENTORNO_COMPLETO = {
    "GROQ_BASE_URL": "https://api.groq.test/openai/v1",
    "GROQ_API_KEY": "clave-groq",
    "GROQ_MODEL": "modelo-groq",
    "OPENAI_BASE_URL": "https://api.openai.test/v1",
    "OPENAI_API_KEY": "clave-openai",
    "OPENAI_MODEL": "modelo-openai",
}


def test_construye_la_cadena_falsa_sin_ninguna_credencial():
    """La condición para que CI corra: sin red y sin variables."""
    cadena = construir_cadena("falso", entorno={})

    assert isinstance(cadena, ProveedorLLM)
    assert cadena.proveedores == ("falso",)


def test_construye_una_cadena_de_varios_proveedores_en_orden():
    cadena = construir_cadena("groq,openai", entorno=ENTORNO_COMPLETO)

    assert cadena.proveedores == ("groq", "openai")
    cadena.cerrar()


def test_un_solo_proveedor_tambien_devuelve_un_enrutador():
    """Para que el resto del sistema no tenga dos formas de recibir un
    proveedor según cuántos haya configurados."""
    cadena = construir_cadena("falso", entorno={})

    assert isinstance(cadena, EnrutadorLLM)


def test_tolera_espacios_y_mayusculas_en_la_ruta():
    cadena = construir_cadena("  GROQ , openai  ", entorno=ENTORNO_COMPLETO)

    assert cadena.proveedores == ("groq", "openai")
    cadena.cerrar()


def test_cambiar_de_proveedor_es_cambiar_la_variable_y_nada_mas():
    """El criterio del enunciado, verificado.

    Se construyen dos cadenas distintas cambiando solo la cadena de texto de
    la ruta, y el mismo Clasificador —sin una línea distinta— trabaja con las
    dos.
    """
    with construir_cadena("falso", entorno={}) as primera:
        clasificador = Clasificador(primera)
        assert clasificador.clasificar("Olvidé mi contraseña") is not None

    with construir_cadena("groq,openai", entorno=ENTORNO_COMPLETO) as segunda:
        assert Clasificador(segunda) is not None
        assert segunda.proveedores == ("groq", "openai")


# ── Configuración inválida: falla al construir, no en producción ────────────


def test_rechaza_una_ruta_vacia():
    with pytest.raises(ConfiguracionInvalida, match="vacía"):
        construir_cadena("", entorno=ENTORNO_COMPLETO)


def test_rechaza_una_ruta_de_solo_comas():
    with pytest.raises(ConfiguracionInvalida, match="vacía"):
        construir_cadena(" , , ", entorno=ENTORNO_COMPLETO)


def test_rechaza_un_proveedor_desconocido_y_dice_cuales_hay():
    with pytest.raises(ConfiguracionInvalida) as error:
        construir_cadena("gemini", entorno=ENTORNO_COMPLETO)

    assert "gemini" in str(error.value)
    assert "groq" in str(error.value)
    assert "falso" in str(error.value)


def test_no_acorta_la_cadena_en_silencio_cuando_falta_una_credencial():
    """Una cadena que uno cree con reserva y no la tiene es peor que una sin
    reserva: el descubrimiento ocurre durante el incidente."""
    entorno = {k: v for k, v in ENTORNO_COMPLETO.items() if not k.startswith("OPENAI")}

    with pytest.raises(ConfiguracionInvalida) as error:
        construir_cadena("groq,openai", entorno=entorno)

    assert "openai" in str(error.value)


def test_el_error_nombra_las_variables_que_faltan():
    with pytest.raises(ConfiguracionInvalida) as error:
        construir_cadena("groq", entorno={"GROQ_API_KEY": "x"})

    assert "GROQ_BASE_URL" in str(error.value)
    assert "GROQ_MODEL" in str(error.value)


def test_el_error_no_revela_el_valor_de_ninguna_credencial():
    """Un mensaje de error que imprime la clave es un secreto filtrado."""
    with pytest.raises(ConfiguracionInvalida) as error:
        construir_cadena("groq,openai", entorno={**ENTORNO_COMPLETO, "OPENAI_MODEL": ""})

    assert "clave-groq" not in str(error.value)
    assert "clave-openai" not in str(error.value)


def test_una_variable_con_solo_espacios_cuenta_como_ausente():
    """Caso de borde real: `GROQ_API_KEY=` en un .env deja una cadena vacía,
    y copiar una línea con espacios deja espacios."""
    with pytest.raises(ConfiguracionInvalida, match="GROQ_API_KEY"):
        construir_cadena("groq", entorno={**ENTORNO_COMPLETO, "GROQ_API_KEY": "   "})


# ── Las dos rutas del sistema ───────────────────────────────────────────────


def test_las_dos_tareas_usan_variables_distintas():
    """ADR-004 §3: clasificar y responder políticas tienen restricciones
    opuestas, así que no comparten cadena."""
    entorno = {
        **ENTORNO_COMPLETO,
        "RUTA_CLASIFICACION": "groq",
        "RUTA_RAG": "openai",
    }

    with construir_para_clasificacion(entorno) as clasificacion:
        assert clasificacion.proveedores == ("groq",)
    with construir_para_rag(entorno) as rag:
        assert rag.proveedores == ("openai",)


def test_sin_variables_las_dos_rutas_caen_en_falso():
    """El valor por defecto es el que hace que CI funcione sin configurar
    nada. Un defecto que exigiera credenciales rompería la suite."""
    assert construir_para_clasificacion({}).proveedores == ("falso",)
    assert construir_para_rag({}).proveedores == ("falso",)


def test_construye_adaptadores_compatibles_para_los_proveedores_reales():
    cadena = construir_cadena("groq", entorno=ENTORNO_COMPLETO)

    assert isinstance(cadena._proveedores[0], AdaptadorCompatible)
    cadena.cerrar()


def test_construye_el_adaptador_falso_para_la_ruta_falsa():
    cadena = construir_cadena("falso", entorno={})

    assert isinstance(cadena._proveedores[0], AdaptadorFalso)

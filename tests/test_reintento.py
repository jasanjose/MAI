"""Pruebas del cálculo de espera entre reintentos."""

from mai.adaptadores.reintento import ESPERA_MAXIMA_S, calcular_espera, leer_retry_after

BASE = 0.5


def test_la_espera_crece_de_forma_exponencial():
    """Cada intento espera al menos el doble de base que el anterior.

    Se comprueban las cotas y no un valor exacto porque el cálculo lleva
    dispersión aleatoria a propósito. Fijar el valor exigiría sembrar el
    generador, y eso probaría el generador, no el retroceso.
    """
    primero = calcular_espera(1, BASE)
    segundo = calcular_espera(2, BASE)
    tercero = calcular_espera(3, BASE)

    assert BASE <= primero < BASE * 2
    assert BASE * 2 <= segundo < BASE * 3
    assert BASE * 4 <= tercero < BASE * 5


def test_respeta_la_espera_que_indica_el_servicio():
    """Si el servicio dice cuánto esperar, se le hace caso."""
    assert calcular_espera(1, BASE, espera_indicada_s=7.0) == 7.0


def test_la_espera_indicada_gana_sobre_el_calculo_propio():
    """Incluso cuando es menor que el retroceso que tocaría."""
    assert calcular_espera(5, BASE, espera_indicada_s=1.0) == 1.0


def test_nunca_supera_el_maximo_por_muchos_intentos_que_pasen():
    """Cota superior: el retroceso exponencial se dispara rápido."""
    assert calcular_espera(20, BASE) == ESPERA_MAXIMA_S


def test_una_espera_indicada_desmedida_tambien_queda_acotada():
    """Un servicio que pide esperar una hora no bloquea el proceso."""
    assert calcular_espera(1, BASE, espera_indicada_s=3600.0) == ESPERA_MAXIMA_S


def test_una_espera_indicada_de_cero_se_respeta():
    """Cero es un valor válido: el servicio dice «reintenta ya»."""
    assert calcular_espera(3, BASE, espera_indicada_s=0.0) == 0.0


def test_un_intento_fuera_de_rango_se_trata_como_el_primero():
    """Caso de borde: llamar con 0 no debe producir un exponente negativo.

    Sin la salvaguarda, `2 ** -1` daría media espera base: una espera
    minúscula justo cuando el servicio acaba de fallar.
    """
    assert BASE <= calcular_espera(0, BASE) < BASE * 2
    assert BASE <= calcular_espera(-5, BASE) < BASE * 2


# ── leer_retry_after ────────────────────────────────────────────────────────


def test_lee_los_segundos_de_retry_after():
    assert leer_retry_after("5") == 5.0


def test_lee_retry_after_con_espacios_alrededor():
    assert leer_retry_after("  5  ") == 5.0


def test_devuelve_none_si_la_cabecera_no_viene():
    assert leer_retry_after(None) is None


def test_devuelve_none_ante_una_fecha_http():
    """La especificación la permite; aquí no se interpreta, se ignora.

    Adivinar mal una fecha produciría una espera arbitraria. Devolver None
    hace que el llamador caiga al retroceso calculado, que es correcto.
    """
    assert leer_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None


def test_devuelve_none_ante_un_valor_que_no_es_numero():
    assert leer_retry_after("pronto") is None
    assert leer_retry_after("") is None
    assert leer_retry_after("-3") is None
    assert leer_retry_after("2.5") is None

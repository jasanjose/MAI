"""Pruebas del clasificador clásico."""

import pytest

from mai.evaluacion.clasificador_clasico import (
    NaiveBayes,
    matriz_de_confusion,
    metricas_por_categoria,
)

TEXTOS = [
    "No puedo entrar al sistema, olvidé mi contraseña",
    "Se bloqueó mi usuario tras varios intentos fallidos",
    "Necesito acceso a la carpeta compartida",
    "El teclado dejó de responder y el monitor parpadea",
    "Mi computador no enciende desde ayer",
    "La impresora del piso tres no imprime",
]
ETIQUETAS = ["Accesos", "Accesos", "Accesos", "Hardware", "Hardware", "Hardware"]


@pytest.fixture
def modelo():
    m = NaiveBayes()
    m.entrenar(TEXTOS, ETIQUETAS)
    return m


# ── Entrenamiento ───────────────────────────────────────────────────────────


def test_aprende_las_categorias_del_historico(modelo):
    assert modelo.categorias == ["Accesos", "Hardware"]


def test_clasifica_un_texto_del_vocabulario_aprendido(modelo):
    assert modelo.predecir("olvidé mi contraseña del sistema").categoria == "Accesos"
    assert modelo.predecir("el monitor no enciende").categoria == "Hardware"


def test_rechaza_entrenar_con_una_sola_categoria():
    """Un clasificador de una sola clase no clasifica. Fallar aquí es mejor
    que devolver siempre lo mismo con aspecto de haber aprendido."""
    with pytest.raises(ValueError, match="dos categorías"):
        NaiveBayes().entrenar(["a", "b"], ["X", "X"])


def test_rechaza_textos_y_etiquetas_desparejados():
    with pytest.raises(ValueError, match="etiqueta"):
        NaiveBayes().entrenar(["a", "b"], ["X"])


def test_predecir_sin_entrenar_falla_en_vez_de_devolver_algo():
    with pytest.raises(RuntimeError, match="entrenado"):
        NaiveBayes().predecir("cualquier cosa")


# ── Casos de borde ──────────────────────────────────────────────────────────


def test_un_texto_sin_terminos_conocidos_no_falla(modelo):
    """Devuelve algo con margen cero: es lo único que se puede decir sin
    evidencia, y el margen lo declara."""
    prediccion = modelo.predecir("xilófono berenjena tramontana")

    assert prediccion.categoria in modelo.categorias
    assert prediccion.margen == 0.0


def test_un_texto_vacio_no_falla(modelo):
    assert modelo.predecir("").categoria in modelo.categorias


def test_el_margen_es_mayor_cuando_el_texto_es_claro(modelo):
    """El margen es la señal para enviar un caso al modelo de lenguaje en vez
    de confiar en el clasificador barato."""
    claro = modelo.predecir("contraseña usuario bloqueado acceso")
    ambiguo = modelo.predecir("")

    assert claro.margen > ambiguo.margen


def test_el_suavizado_evita_que_una_palabra_desconocida_anule_una_categoria():
    """Sin suavizado, un término con probabilidad cero anularía todo el
    producto: una sola palabra descartaría la categoría correcta."""
    m = NaiveBayes()
    m.entrenar(TEXTOS, ETIQUETAS)

    # «impresora» solo aparece en Hardware; «contraseña» solo en Accesos.
    assert m.predecir("contraseña impresora").categoria in m.categorias


# ── Matriz de confusión ─────────────────────────────────────────────────────


def test_la_matriz_cuenta_aciertos_en_la_diagonal():
    matriz = matriz_de_confusion(
        ["A", "A", "B"], ["A", "B", "B"], ["A", "B"]
    )

    assert matriz["A"]["A"] == 1
    assert matriz["A"]["B"] == 1
    assert matriz["B"]["B"] == 1


def test_la_matriz_incluye_las_categorias_sin_casos():
    """Una categoría ausente de la prueba debe aparecer en ceros, no faltar:
    su ausencia es información."""
    matriz = matriz_de_confusion(["A"], ["A"], ["A", "B", "C"])

    assert set(matriz) == {"A", "B", "C"}
    assert matriz["B"] == {"A": 0, "B": 0, "C": 0}


def test_calcula_precision_exhaustividad_y_f1():
    matriz = matriz_de_confusion(
        ["A", "A", "B", "B"], ["A", "B", "B", "B"], ["A", "B"]
    )
    m = metricas_por_categoria(matriz)

    assert m["A"]["precision"] == 1.0
    assert m["A"]["exhaustividad"] == 0.5
    assert m["B"]["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["B"]["exhaustividad"] == 1.0


def test_una_categoria_nunca_predicha_no_divide_por_cero():
    matriz = matriz_de_confusion(["A", "B"], ["A", "A"], ["A", "B"])

    assert metricas_por_categoria(matriz)["B"]["precision"] == 0.0
    assert metricas_por_categoria(matriz)["B"]["f1"] == 0.0

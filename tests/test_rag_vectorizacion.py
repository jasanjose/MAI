"""Pruebas de la vectorización TF-IDF."""

import pytest

from mai.dominio.puertos import Vectorizador
from mai.rag.vectorizacion import VectorizadorTFIDF, coseno, tokenizar

CORPUS = [
    "Solicitud y aprobación La solicitud debe radicarse con una anticipación mínima "
    "de quince (15) días calendario.",
    "Contraseñas La longitud mínima es de doce (12) caracteres con mayúsculas y números.",
    "Montos máximos diarios Hospedaje noventa mil pesos en ciudades capitales.",
    "Reapertura Un ticket cerrado puede reabrirse dentro de los tres días siguientes.",
]


@pytest.fixture
def vectorizador():
    v = VectorizadorTFIDF()
    v.indexar(CORPUS)
    return v


# ── Tokenización ────────────────────────────────────────────────────────────


def test_pasa_a_minusculas_y_quita_tildes():
    """Sin quitar tildes, «anticipación» y «anticipacion» serían términos
    distintos — el mismo defecto que ya apareció en las reglas de
    clasificación."""
    assert tokenizar("Anticipación") == tokenizar("anticipacion") == ["anticipacion"]


def test_conserva_los_numeros():
    """El corpus está lleno de plazos y montos, y quien pregunta escribe el
    número: «¿cuántos días?» contra «quince (15) días»."""
    assert "15" in tokenizar("quince (15) días hábiles")


def test_descarta_las_palabras_de_una_letra():
    assert tokenizar("a b si no") == []


def test_descarta_los_interrogativos():
    """No aparecen nunca en un documento normativo, así que su IDF es alto y
    dominan la consulta sin aportar nada. Es la causa medida de que sin esta
    lista el margen de abstención sea negativo."""
    assert tokenizar("¿cuál es la política de teletrabajo?") == ["politica", "teletrabajo"]


def test_no_falla_con_texto_vacio_o_nulo():
    assert tokenizar("") == []
    assert tokenizar(None) == []


def test_separa_por_signos_de_puntuacion():
    assert tokenizar("hurto, daño; pérdida.") == ["hurto", "dano", "perdida"]


# ── Contrato del puerto ─────────────────────────────────────────────────────


def test_cumple_el_contrato_del_puerto(vectorizador):
    assert isinstance(vectorizador, Vectorizador)
    assert vectorizador.nombre == "tfidf"


def test_consultar_antes_de_indexar_falla_en_vez_de_devolver_basura():
    """Vectorizar con otro vocabulario produciría similitudes que parecen
    números y no significan nada. Fallar es mejor."""
    with pytest.raises(RuntimeError, match="indexar"):
        VectorizadorTFIDF().consultar("cualquier cosa")


# ── Vectores ────────────────────────────────────────────────────────────────


def test_produce_un_vector_por_documento(vectorizador):
    vectores = VectorizadorTFIDF().indexar(CORPUS)

    assert len(vectores) == len(CORPUS)


def test_todos_los_vectores_tienen_el_mismo_tamano(vectorizador):
    vectores = VectorizadorTFIDF().indexar(CORPUS)

    assert len({len(v) for v in vectores}) == 1


def test_los_vectores_quedan_normalizados(vectorizador):
    """Longitud 1, para que el coseno sea el producto punto y un fragmento
    largo no gane por ser largo."""
    for vector in VectorizadorTFIDF().indexar(CORPUS):
        assert abs(sum(x * x for x in vector) - 1.0) < 1e-9


def test_es_determinista():
    """La razón de elegirlo: mismo corpus, mismos vectores, siempre."""
    primero = VectorizadorTFIDF().indexar(CORPUS)
    segundo = VectorizadorTFIDF().indexar(CORPUS)

    assert primero == segundo


def test_un_corpus_vacio_no_falla():
    assert VectorizadorTFIDF().indexar([]) == []


def test_un_documento_sin_terminos_utiles_da_el_vector_nulo():
    """Caso de borde: dividir por una norma cero."""
    vectores = VectorizadorTFIDF().indexar(["contraseña larga", "de la el"])

    assert all(x == 0.0 for x in vectores[1])


# ── Recuperación ────────────────────────────────────────────────────────────


def _mejor(vectorizador, consulta):
    vectores = vectorizador.indexar(CORPUS)
    puntajes = [coseno(vectorizador.consultar(consulta), v) for v in vectores]
    return puntajes.index(max(puntajes)), max(puntajes)


def test_recupera_el_fragmento_que_comparte_vocabulario(vectorizador):
    indice, puntaje = _mejor(vectorizador, "¿cuántos días de anticipación para la solicitud?")

    assert indice == 0
    assert puntaje > 0


def test_recupera_por_el_titulo_heredado_y_no_solo_por_el_cuerpo(vectorizador):
    """«Hospedaje» está en el título de la sección; el cuerpo podría no
    repetirlo nunca."""
    indice, _ = _mejor(vectorizador, "hospedaje")

    assert indice == 2


def test_una_consulta_sin_terminos_conocidos_puntua_cero(vectorizador):
    """La señal de que no hay evidencia. Si el vector de la consulta es nulo,
    su similitud con todo el corpus es cero."""
    vectores = vectorizador.indexar(CORPUS)
    consulta = vectorizador.consultar("teletrabajo mascotas criptomonedas")

    assert all(coseno(consulta, v) == 0.0 for v in vectores)


def test_repetir_una_palabra_no_multiplica_la_relevancia():
    """1 + log(n): el quinto uso aporta menos que el segundo."""
    v = VectorizadorTFIDF()
    vectores = v.indexar(["hospedaje", "hospedaje hospedaje hospedaje hospedaje hospedaje"])

    assert vectores[0] == vectores[1]  # ambos normalizados a un solo término


# ── Coseno ──────────────────────────────────────────────────────────────────


def test_el_coseno_de_un_vector_consigo_mismo_es_uno():
    vector = VectorizadorTFIDF().indexar(CORPUS)[0]

    assert abs(coseno(vector, vector) - 1.0) < 1e-9


def test_el_coseno_con_el_vector_nulo_es_cero():
    vector = VectorizadorTFIDF().indexar(CORPUS)[0]

    assert coseno(vector, tuple([0.0] * len(vector))) == 0.0


def test_comparar_vectores_de_tamanos_distintos_falla():
    """Daría un número plausible y sin sentido, que es peor que un error."""
    with pytest.raises(ValueError, match="tamaños distintos"):
        coseno((1.0, 0.0), (1.0, 0.0, 0.0))

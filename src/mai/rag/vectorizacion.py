"""Vectorización TF-IDF, en Python puro.

**Por qué contar palabras y no un modelo de embeddings.** El corpus son 67
fragmentos de unas 25 palabras. A esa escala, un modelo de embeddings aporta
sobre todo la capacidad de reconocer sinónimos —«vacaciones» y «descanso
remunerado»—, y cuesta descargar ~90 MB de pesos o llamar a un servicio
remoto en cada consulta. Lo primero rompe que las pruebas corran sin red; lo
segundo, que corran sin credenciales.

TF-IDF no reconoce sinónimos, y eso es un límite real y declarado. A cambio
es determinista, instantáneo, y **explicable término a término**: se puede
señalar exactamente qué palabra hizo que un fragmento saliera primero. Sobre
un corpus normativo, donde quien pregunta suele usar el vocabulario del
documento —«viáticos», «reapertura», «anticipo»—, esa desventaja pesa menos
de lo que parece.

La decisión no cierra la puerta: el vectorizador remoto implementa el mismo
puerto y se elige por configuración. Cuál recupera mejor sobre este corpus es
una pregunta empírica, y se puede medir.

## Cómo funciona, en tres pasos

1. **TF** — cuántas veces aparece un término en un fragmento, suavizado con
   `1 + log(n)`. Sin el logaritmo, un fragmento que repite «acceso» cinco
   veces parecería cinco veces más relevante que uno que la dice una vez, y
   no lo es.
2. **IDF** — cuánta información aporta el término, `log((1+N)/(1+df)) + 1`.
   Un término que aparece en todos los fragmentos no distingue nada y su peso
   tiende a cero. Esto es lo que hace innecesaria una lista de palabras vacías
   en español: «de», «la» y «que» se anulan solas.
3. **Normalización L2** — deja todos los vectores de longitud 1, con lo que
   el coseno entre dos es su producto punto. Sin esto, un fragmento largo
   ganaría por ser largo.

## Por qué hay lista de palabras vacías si el IDF debería bastar

El IDF anula solo las palabras frecuentes **en el corpus**. Los interrogativos
—«cuál», «cuánto», «debo»— no aparecen nunca en un documento normativo, así
que su IDF es alto y dominan la consulta sin aportar nada. El efecto está
medido sobre un conjunto de ocho preguntas con respuesta verificada y tres
sin respaldo:

    sin lista:  recall@1 3/8 · recall@3 5/8 · margen de abstención -0.107
    con lista:  recall@1 4/8 · recall@3 6/8 · margen de abstención +0.009

El margen es la distancia entre la peor puntuación de una pregunta con
respuesta y la mejor de una sin respaldo. **Sin la lista es negativo**: una
pregunta sobre teletrabajo, que el corpus no cubre, puntúa más alto que una
pregunta legítima. Con margen negativo no existe ningún umbral de abstención
que funcione, por bien que se calibre.

## El límite de todo esto, medido

«¿Qué pasa si pierdo el computador asignado?» no recupera `POL-TIC-02 §5.1`,
que es su respuesta. El fragmento dice *«Pérdida, hurto o daño. La novedad
debe reportarse…»*: no comparte **ni un término de contenido** con la
pregunta. `pierdo` contra `perdida` es morfología, y `computador` no aparece
porque el documento dice «novedad».

Un stemmer de sufijos tampoco lo resolvería: `pierdo` y `pérdida` difieren en
la diptongación de la raíz, que los stemmers no deshacen. Es el límite real
de la recuperación léxica y la razón concreta por la que el vectorizador
remoto implementa el mismo puerto.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from mai.dominio.puertos import Vector, Vectorizador

# Se conservan los dígitos: el corpus está lleno de plazos y montos —«quince
# (15) días», «tres (3) días hábiles»— y quien pregunta escribe el número.
_TOKEN = re.compile(r"[a-z0-9]+")

LARGO_MINIMO_TOKEN = 2

# Palabras que no discriminan. Dos grupos con motivos distintos:
#
# Las de función —artículos, preposiciones, pronombres— aparecen en casi
# todos los fragmentos, así que el IDF ya las anula casi del todo. Quitarlas
# es sobre todo ahorro de dimensiones.
#
# Las interrogativas son el caso que de verdad importa: «cuál», «cuánto» y
# «debo» **no aparecen nunca** en un documento normativo, así que su IDF es
# alto y dominan la consulta aportando cero información. Son la causa medida
# de que sin esta lista el margen de abstención sea negativo.
PALABRAS_VACIAS = frozenset(
    """
    el la los las un una unos unas de del al a en con por para y o u e que se
    su sus lo le les es son ser fue ha han este esta estos estas ese esa eso
    mi mis me te tu nos si no mas muy ya como cuando donde desde hasta sobre
    entre sin tras cada otro otra todo toda
    cual cuales cuanto cuanta cuantos cuantas quien quienes porque
    debo puedo necesito quiero tengo hay pasa
    """.split()
)


def tokenizar(texto: str) -> list[str]:
    """Parte el texto en términos comparables: minúsculas y sin tildes.

    Sin quitar tildes, «anticipación» y «anticipacion» serían términos
    distintos y una consulta sin acentos no encontraría nada — el mismo
    defecto que ya apareció en las reglas de clasificación.

    Los términos de una sola letra y las palabras vacías se descartan: no
    distinguen fragmentos. Ver `PALABRAS_VACIAS` para por qué los
    interrogativos son el caso que importa.
    """
    sin_tildes = "".join(
        c
        for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return [
        t
        for t in _TOKEN.findall(sin_tildes)
        if len(t) >= LARGO_MINIMO_TOKEN and t not in PALABRAS_VACIAS
    ]


def coseno(a: Vector, b: Vector) -> float:
    """Similitud entre dos vectores ya normalizados: su producto punto.

    Se comprueba la longitud en vez de confiar: comparar vectores de
    vocabularios distintos daría un número plausible y sin sentido, que es
    peor que un error.
    """
    if len(a) != len(b):
        raise ValueError(
            f"No se pueden comparar vectores de tamaños distintos ({len(a)} y {len(b)}). "
            "Probablemente se vectorizó la consulta con otro vocabulario."
        )
    return sum(x * y for x, y in zip(a, b, strict=True))


class VectorizadorTFIDF(Vectorizador):
    """TF-IDF sobre el vocabulario del corpus indexado."""

    def __init__(self) -> None:
        self._vocabulario: dict[str, int] = {}
        self._idf: list[float] = []
        self._indexado = False

    @property
    def nombre(self) -> str:
        return "tfidf"

    def indexar(self, textos: Sequence[str]) -> list[Vector]:
        """Aprende el vocabulario y el IDF, y devuelve los vectores del corpus."""
        documentos = [tokenizar(t) for t in textos]

        terminos = sorted({termino for doc in documentos for termino in doc})
        self._vocabulario = {termino: i for i, termino in enumerate(terminos)}

        total = len(documentos)
        apariciones = Counter(termino for doc in documentos for termino in set(doc))
        # El suavizado (+1 arriba y abajo) evita dividir por cero con un
        # término que no esté en ningún documento, y el +1 final impide que un
        # término presente en todos quede en peso exactamente cero: seguiría
        # aportando algo si dos fragmentos empatan en todo lo demás.
        self._idf = [
            math.log((1 + total) / (1 + apariciones[termino])) + 1 for termino in terminos
        ]
        self._indexado = True

        return [self._vectorizar(doc) for doc in documentos]

    def consultar(self, texto: str) -> Vector:
        """Vectoriza una consulta con el vocabulario aprendido.

        Los términos de la consulta que no estén en el corpus se ignoran. No
        es una pérdida: un término que no aparece en ningún fragmento no puede
        ayudar a elegir entre ellos. Y si **todos** los términos son
        desconocidos, el vector queda en cero y la similitud con todo será
        cero — que es exactamente la señal de que no hay evidencia.
        """
        if not self._indexado:
            raise RuntimeError(
                "El vectorizador no ha indexado ningún corpus. Llame a `indexar` "
                "antes de `consultar`: vectorizar con otro vocabulario produciría "
                "similitudes sin sentido."
            )
        return self._vectorizar(tokenizar(texto))

    # ── Interno ─────────────────────────────────────────────────────────────

    def _vectorizar(self, terminos: Sequence[str]) -> Vector:
        pesos = [0.0] * len(self._vocabulario)
        if not terminos:
            return tuple(pesos)

        for termino, veces in Counter(terminos).items():
            indice = self._vocabulario.get(termino)
            if indice is None:
                continue
            # 1 + log(n): el quinto uso de una palabra aporta menos que el
            # segundo. Repetir no multiplica la relevancia.
            pesos[indice] = (1 + math.log(veces)) * self._idf[indice]

        norma = math.sqrt(sum(p * p for p in pesos))
        if norma == 0:
            # Ningún término conocido. Se devuelve el vector nulo en vez de
            # dividir por cero: su similitud con todo será cero, que es la
            # señal correcta.
            return tuple(pesos)
        return tuple(p / norma for p in pesos)

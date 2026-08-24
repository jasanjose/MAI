"""Clasificador supervisado clásico: Naive Bayes multinomial.

**Por qué escrito y no traído de una biblioteca.** El estándar del proyecto
pregunta si la biblioteca estándar resuelve el problema en menos de treinta
líneas comprensibles. Aquí sí: el tokenizador ya existe —se comparte con el
componente de recuperación— y Naive Bayes multinomial sobre conteos de
términos son unas treinta líneas de aritmética que se pueden explicar en voz
alta.

Traer `scikit-learn` para esto añadiría una dependencia grande, con su cadena
de dependencias numéricas, para reemplazar código que cabe en una pantalla —y
que hay que entender igual, porque el resultado se presenta al negocio.

Lo que **sí** se pierde: validación cruzada, búsqueda de hiperparámetros y
una docena de modelos alternativos listos para comparar. Se acepta porque el
objetivo es una **línea base honesta** contra la que comparar el modelo de
lenguaje, no exprimir el último punto de precisión.

## Cómo funciona, para poder defenderlo

Naive Bayes calcula, para cada categoría, la probabilidad de que un texto
pertenezca a ella, y se queda con la mayor:

    P(categoría | texto)  ∝  P(categoría) · ∏ P(término | categoría)

- **P(categoría)** es cuántos tickets de esa categoría hay en el histórico.
- **P(término | categoría)** es cuántas veces aparece ese término en esa
  categoría, sobre el total de términos de la categoría.
- Se suman logaritmos en vez de multiplicar probabilidades: con cincuenta
  términos, el producto se hunde por debajo de la precisión del punto
  flotante y todo daría cero.

**«Naive»** es porque supone que los términos son independientes entre sí —que
«no» y «funciona» aportan por separado—. Es falso, y aun así funciona bien
para clasificar texto: no necesita estimar bien la probabilidad, solo
ordenar las categorías correctamente.

**Suavizado de Laplace:** un término que nunca apareció en una categoría
tendría probabilidad cero y anularía todo el producto — una sola palabra
desconocida descartaría la categoría correcta. Sumar 1 a cada conteo lo evita.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from mai.rag.vectorizacion import tokenizar

SUAVIZADO = 1.0


@dataclass(frozen=True)
class Prediccion:
    """Categoría elegida y qué tan seguro está el modelo.

    `margen` es la diferencia de log-probabilidad con la segunda candidata.
    Un margen pequeño significa que el modelo casi eligió otra cosa, y es la
    señal para enviar ese caso al modelo de lenguaje en vez de confiar.
    """

    categoria: str
    margen: float


class NaiveBayes:
    """Clasificador multinomial sobre conteos de términos."""

    def __init__(self, suavizado: float = SUAVIZADO) -> None:
        self._suavizado = suavizado
        self._log_previa: dict[str, float] = {}
        self._log_verosimilitud: dict[str, dict[str, float]] = {}
        self._log_desconocido: dict[str, float] = {}
        self._vocabulario: set[str] = set()
        self.categorias: list[str] = []

    def entrenar(self, textos: Sequence[str], etiquetas: Sequence[str]) -> None:
        """Aprende del histórico etiquetado.

        Lanza `ValueError` con menos de dos categorías: un clasificador de una
        sola clase no clasifica, y fallar aquí es mejor que devolver siempre
        lo mismo con aspecto de haber aprendido.
        """
        if len(textos) != len(etiquetas):
            raise ValueError("Cada texto necesita su etiqueta.")
        if len(set(etiquetas)) < 2:
            raise ValueError("Hacen falta al menos dos categorías para entrenar.")

        conteos: dict[str, Counter[str]] = defaultdict(Counter)
        documentos = Counter(etiquetas)

        for texto, etiqueta in zip(textos, etiquetas, strict=True):
            terminos = tokenizar(texto)
            conteos[etiqueta].update(terminos)
            self._vocabulario.update(terminos)

        total = len(etiquetas)
        tamano_vocabulario = len(self._vocabulario)
        self.categorias = sorted(documentos)

        for categoria in self.categorias:
            self._log_previa[categoria] = math.log(documentos[categoria] / total)

            terminos_categoria = sum(conteos[categoria].values())
            denominador = terminos_categoria + self._suavizado * tamano_vocabulario

            self._log_verosimilitud[categoria] = {
                termino: math.log((veces + self._suavizado) / denominador)
                for termino, veces in conteos[categoria].items()
            }
            # Un término del vocabulario que no apareció en ESTA categoría.
            self._log_desconocido[categoria] = math.log(self._suavizado / denominador)

    def predecir(self, texto: str) -> Prediccion:
        """Categoría más probable, con el margen sobre la segunda.

        Ante un texto sin términos conocidos devuelve la categoría más
        frecuente con margen cero: es lo único que se puede decir sin
        evidencia, y el margen cero lo declara.
        """
        if not self._log_previa:
            raise RuntimeError("El clasificador no ha sido entrenado.")

        terminos = [t for t in tokenizar(texto) if t in self._vocabulario]
        puntajes: list[tuple[float, str]] = []

        for categoria in self.categorias:
            verosimilitud = self._log_verosimilitud[categoria]
            desconocido = self._log_desconocido[categoria]
            puntaje = self._log_previa[categoria] + sum(
                verosimilitud.get(t, desconocido) for t in terminos
            )
            puntajes.append((puntaje, categoria))

        puntajes.sort(reverse=True)
        margen = puntajes[0][0] - puntajes[1][0] if len(puntajes) > 1 else 0.0
        return Prediccion(categoria=puntajes[0][1], margen=round(margen, 4))


def matriz_de_confusion(
    reales: Sequence[str], predichas: Sequence[str], categorias: Sequence[str]
) -> dict[str, dict[str, int]]:
    """Cuántas veces cada categoría real se predijo como cada otra.

    La diagonal son los aciertos; **lo interesante está fuera de ella**. Una
    precisión global esconde que el modelo confunde sistemáticamente dos
    categorías concretas, y esa confusión es la que hay que llevar al negocio.
    """
    matriz = {real: dict.fromkeys(categorias, 0) for real in categorias}
    for real, predicha in zip(reales, predichas, strict=True):
        matriz[real][predicha] += 1
    return matriz


def metricas_por_categoria(matriz: dict[str, dict[str, int]]) -> dict[str, dict[str, float]]:
    """Precisión, exhaustividad y F1 por categoría.

    Se reportan las tres y no solo la precisión global porque **las
    categorías no valen lo mismo ni tienen el mismo tamaño**: un modelo que
    acierta el 90 % global puede estar fallando por completo en la categoría
    con menos ejemplos, y esa suele ser la que importa.
    """
    resultado: dict[str, dict[str, float]] = {}
    for categoria in matriz:
        verdaderos = matriz[categoria][categoria]
        predichos = sum(matriz[real][categoria] for real in matriz)
        reales = sum(matriz[categoria].values())

        precision = verdaderos / predichos if predichos else 0.0
        exhaustividad = verdaderos / reales if reales else 0.0
        f1 = (
            2 * precision * exhaustividad / (precision + exhaustividad)
            if precision + exhaustividad
            else 0.0
        )
        resultado[categoria] = {
            "precision": round(precision, 4),
            "exhaustividad": round(exhaustividad, 4),
            "f1": round(f1, 4),
            "casos": reales,
        }
    return resultado

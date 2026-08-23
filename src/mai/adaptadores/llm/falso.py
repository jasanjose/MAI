"""Proveedor de lenguaje determinista, sin red.

No es un atajo de conveniencia. Es lo que permite que la suite completa corra
en integración continua **sin credenciales, sin red y con el mismo resultado
en cada ejecución**. Un sistema cuyas pruebas dependen de un proveedor remoto
no tiene pruebas: tiene un monitoreo caro e intermitente.

Este adaptador **no contiene lógica de negocio**. No sabe qué es una
categoría ni cómo se clasifica un ticket. Devuelve el texto que se le dio al
construirlo. Quién decide ese texto es quien compone el sistema —una prueba o
la fábrica—, y ahí es donde ese conocimiento corresponde.

También sabe fallar, porque el modo degradado y la cadena de reserva no se
pueden probar contra un proveedor que siempre responde.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from mai.dominio.puertos import ProveedorLLM, ProveedorNoDisponible, RespuestaLLM

RESPUESTA_POR_DEFECTO = "(respuesta de prueba)"
MODELO_FALSO = "determinista-v1"


class AdaptadorFalso(ProveedorLLM):
    """Proveedor que devuelve respuestas fijadas de antemano.

    - `respuestas`: los textos a devolver, en orden. Agotada la lista, repite
      el último. Con una sola respuesta se comporta como constante.
    - `fallos_iniciales`: cuántas de las primeras llamadas lanzan
      `ProveedorNoDisponible` antes de empezar a responder. Sirve para probar
      el reintento y la cadena de reserva.
    - `falla_siempre`: nunca responde. Sirve para probar que la cadena se
      agota y entra el modo degradado.

    Registra cada llamada en `self.llamadas` como `(instruccion, entrada)`.
    Eso permite verificar algo que no se puede ver desde la respuesta: que el
    texto del usuario viajó por el canal de entrada y **nunca** se coló en la
    instrucción.
    """

    def __init__(
        self,
        respuestas: Sequence[str] | None = None,
        fallos_iniciales: int = 0,
        falla_siempre: bool = False,
        nombre: str = "falso",
    ) -> None:
        self._respuestas = list(respuestas) if respuestas else [RESPUESTA_POR_DEFECTO]
        self._fallos_iniciales = max(0, fallos_iniciales)
        self._falla_siempre = falla_siempre
        self._nombre = nombre
        self.llamadas: list[tuple[str, str]] = []

    @property
    def nombre(self) -> str:
        return self._nombre

    def completar(self, instruccion: str, entrada: str) -> RespuestaLLM:
        """Devuelve la respuesta que toque, o falla si así se configuró."""
        inicio = time.monotonic()
        self.llamadas.append((instruccion, entrada))
        numero_de_llamada = len(self.llamadas)

        if self._falla_siempre or numero_de_llamada <= self._fallos_iniciales:
            raise ProveedorNoDisponible(
                f"El proveedor «{self._nombre}» no respondió. "
                "Intente más tarde o revise la configuración del proveedor."
            )

        # Agotada la lista se repite el último: un proveedor no deja de
        # responder porque se le acaben las respuestas preparadas.
        indice = min(numero_de_llamada - self._fallos_iniciales, len(self._respuestas)) - 1

        return RespuestaLLM(
            texto=self._respuestas[indice],
            proveedor=self._nombre,
            modelo=MODELO_FALSO,
            latencia_ms=round((time.monotonic() - inicio) * 1000, 2),
            # Un proveedor falso no consume tokens. Se declara ausente en vez
            # de fingir un cero: un cero se suma en los agregados y ensucia el
            # costo estimado; un None se ve y se excluye.
            tokens_entrada=None,
            tokens_salida=None,
        )

"""Índice de fragmentos en memoria.

**No hay base vectorial, y esa es la decisión.** El corpus son 67 fragmentos.
Buscar entre ellos es recorrer una lista de 67 productos punto: microsegundos.
Chroma o FAISS aquí serían una dependencia que no acelera nada medible, que
hay que instalar, versionar y mantener, y que habría que explicar. Traer una
biblioteca de índices aproximados para 67 elementos es resolver un problema
que no se tiene.

**Bajo qué condición cambiaría.** Un índice exacto sobre lista se vuelve
incómodo cuando el corpus llega a unos miles de fragmentos y la búsqueda deja
de ser instantánea, o cuando hace falta persistirlo entre reinicios en vez de
reconstruirlo. Con cinco políticas de dos páginas, ninguna de las dos se
cumple ni de lejos.

El índice implementa `RecuperadorDeFragmentos`, así que el día que haga falta
una base vectorial entra como otro adaptador y el servicio de consulta no se
entera.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from mai.dominio.politicas import Coincidencia, Fragmento, RecuperadorDeFragmentos
from mai.dominio.puertos import Vectorizador
from mai.rag.vectorizacion import Vector, coseno

logger = logging.getLogger(__name__)


class IndiceEnMemoria(RecuperadorDeFragmentos):
    """Búsqueda exacta por similitud de coseno sobre una lista.

    Se construye con los fragmentos y un vectorizador. El vectorizador aprende
    del corpus al indexar, así que **un índice y su vectorizador van juntos**:
    consultar con otro produciría vectores de vocabularios distintos.
    """

    def __init__(self, fragmentos: Sequence[Fragmento], vectorizador: Vectorizador) -> None:
        self._fragmentos = list(fragmentos)
        self._vectorizador = vectorizador
        self._vectores: list[Vector] = vectorizador.indexar(
            [f.texto_para_buscar for f in self._fragmentos]
        )
        logger.info(
            "indice_construido",
            extra={
                "fragmentos": len(self._fragmentos),
                "vectorizador": vectorizador.nombre,
                "dimensiones": len(self._vectores[0]) if self._vectores else 0,
            },
        )

    def __len__(self) -> int:
        return len(self._fragmentos)

    def buscar(self, consulta: str, cuantos: int) -> list[Coincidencia]:
        """Los `cuantos` fragmentos más parecidos, de mayor a menor puntaje.

        Un índice vacío devuelve lista vacía en vez de fallar: que aún no haya
        políticas cargadas es un estado válido del sistema, y el servicio de
        consulta ya sabe abstenerse cuando no hay evidencia.

        Se devuelven también las coincidencias de puntaje cero cuando caben en
        `cuantos`. Filtrarlas aquí escondería información: quien decide si hay
        evidencia suficiente es el servicio, con su umbral, y para eso necesita
        ver el puntaje real — incluido el cero.
        """
        if not self._fragmentos or cuantos <= 0:
            return []

        vector_consulta = self._vectorizador.consultar(consulta)
        coincidencias = [
            Coincidencia(fragmento=fragmento, puntaje=coseno(vector_consulta, vector))
            for fragmento, vector in zip(self._fragmentos, self._vectores, strict=True)
        ]
        # `-puntaje` primero y la cita después: con puntajes empatados el orden
        # debe ser estable y reproducible, no el que traía la lista.
        coincidencias.sort(key=lambda c: (-c.puntaje, c.fragmento.cita))
        return coincidencias[:cuantos]

"""Registro de claves de idempotencia en memoria.

Sobre la durabilidad, que es la objeción esperable: estas claves se pierden
al reiniciar el proceso. En este sistema eso **no abre un agujero**, porque
las solicitudes viven en el mismo sitio (D-005): si el proceso reinicia, no
queda ningún recurso que se pueda duplicar. El almacén de claves tiene
exactamente la misma durabilidad que los recursos que protege.

El día que la persistencia pase a SQL, esa simetría se rompe y esta clase
deja de servir: ahí la indivisibilidad la debe dar una restricción
`UNIQUE(clave)` en la tabla, no un cerrojo de proceso, porque con varios
procesos sirviendo la API un cerrojo local no protege nada.

## Dos límites declarados, medidos

**No hay caducidad.** Una clave completada se conserva indefinidamente. Se
midió: 10.000 claves únicas dejan 10.000 entradas retenidas. Un cliente que
genere una clave nueva por petición hace crecer la memoria sin techo. Los
almacenes de idempotencia reales caducan las claves —24 horas es lo
habitual—, porque pasado ese plazo ningún reintento razonable va a llegar.
No se implementa aquí: exige una tarea de limpieza o marcas de tiempo por
entrada, y con almacenamiento en memoria el proceso se reinicia mucho antes
de que el crecimiento importe. Con persistencia real deja de ser aceptable.

**Una reserva sin terminar puede quedarse.** `liberar` la suelta cuando la
operación falla, pero si el proceso muere entre reservar y completar, la
entrada queda en «en curso» y los reintentos de esa clave reciben 409 para
siempre. Aquí no llega a ocurrir —si el proceso muere, el diccionario muere
con él—, pero es el mismo problema que la caducidad y se resuelve igual.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from mai.dominio.idempotencia import (
    RESERVA_CONFLICTO,
    RESERVA_EN_CURSO,
    RESERVA_NUEVA,
    RESERVA_REPETIDA,
    RegistroDeIdempotencia,
    Reserva,
)


@dataclass
class _Entrada:
    """Lo guardado por clave. `codigo` en None significa «reservada, sin terminar»."""

    huella: str
    codigo: str | None = None


class RegistroIdempotenciaEnMemoria(RegistroDeIdempotencia):
    """Claves en un diccionario del proceso, protegido por un cerrojo."""

    def __init__(self) -> None:
        self._entradas: dict[str, _Entrada] = {}
        self._cerrojo = threading.RLock()

    def reservar(self, clave: str, huella: str) -> Reserva:
        """Consulta y reserva sin soltar el cerrojo entre las dos cosas.

        Que todo el cuerpo esté dentro del `with` **es** la garantía. Si se
        consultara dentro y se escribiera fuera, dos peticiones simultáneas
        verían las dos que la clave no existe y las dos crearían un recurso.

        Está medido, y el resultado matiza la urgencia sin quitarle la razón:
        con la versión de dos pasos, 64 hilos pidiendo 500 claves devolvieron
        `NUEVA` 501 veces —un duplicado— en una de dos corridas. Bajo el GIL
        la ventana es estrecha y el fallo sale poco. Ese es justamente el
        perfil del defecto que llega a producción y nadie consigue reproducir,
        y la razón de que no se pueda escribir una prueba determinista para
        él.

        El cerrojo se sostiene solo durante esta comparación y escritura, que
        son operaciones de memoria. La parte lenta —clasificar, guardar— pasa
        fuera, con la clave ya reservada, así que dos claves distintas nunca
        se estorban.
        """
        with self._cerrojo:
            entrada = self._entradas.get(clave)

            if entrada is None:
                self._entradas[clave] = _Entrada(huella=huella)
                return Reserva(RESERVA_NUEVA)

            if entrada.huella != huella:
                return Reserva(RESERVA_CONFLICTO)

            if entrada.codigo is None:
                return Reserva(RESERVA_EN_CURSO)

            return Reserva(RESERVA_REPETIDA, codigo=entrada.codigo)

    def completar(self, clave: str, codigo: str) -> None:
        with self._cerrojo:
            entrada = self._entradas.get(clave)
            if entrada is not None:
                entrada.codigo = codigo

    def liberar(self, clave: str) -> None:
        """Suelta la reserva solo si sigue sin terminar.

        La comprobación importa: liberar una entrada ya completada borraría
        una repetición legítima y el siguiente reintento crearía un duplicado.
        """
        with self._cerrojo:
            entrada = self._entradas.get(clave)
            if entrada is not None and entrada.codigo is None:
                del self._entradas[clave]

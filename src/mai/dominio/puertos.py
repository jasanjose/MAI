"""Puertos del dominio: lo que el negocio le pide a la infraestructura.

Este módulo define **qué** se le pide a un modelo de lenguaje, nunca **a
quién** ni **cómo**. No importa `httpx`, ni un SDK de proveedor, ni nada que
represente infraestructura. Esa es la condición que hace posible cambiar de
proveedor sin tocar una línea de lógica de negocio.

Las excepciones también viven aquí, y no en los adaptadores, por un motivo
concreto: el dominio necesita **capturarlas** para decidir el modo degradado.
Si estuvieran definidas en `adaptadores/llm/`, el dominio tendría que
importar el adaptador para atraparlas y la dependencia quedaría invertida —
justo lo que este archivo existe para evitar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

# Un vector es una lista de números. El dominio no sabe si salieron de contar
# palabras o de una red neuronal: solo que se pueden comparar entre sí.
Vector = tuple[float, ...]


class ErrorProveedorLLM(Exception):
    """Base de los fallos del proveedor, ya traducidos a lenguaje del dominio.

    Ninguna excepción de una librería de transporte cruza esta frontera. El
    dominio no sabe que existe `httpx.TimeoutException`.
    """


class ProveedorNoDisponible(ErrorProveedorLLM):
    """El proveedor no respondió correctamente tras agotar los reintentos."""


class RespuestaInutilizable(ErrorProveedorLLM):
    """El proveedor respondió, pero el cuerpo no sirve.

    Se distingue de `ProveedorNoDisponible` porque no se resuelve esperando:
    reintentar una respuesta malformada da otra respuesta malformada.
    """


class CadenaAgotada(ErrorProveedorLLM):
    """Todos los proveedores de la cadena fallaron.

    Es la señal que dispara el modo degradado. La lanza el enrutador; la
    captura el servicio de dominio, que es quien sabe qué significa degradarse
    para cada tarea.
    """


@dataclass(frozen=True)
class RespuestaLLM:
    """Lo que devuelve una llamada al modelo, con su medición incorporada.

    La medición no es opcional ni va en un canal aparte: viaja con la
    respuesta. El estándar §7 exige registrar latencia y tokens en toda
    llamada a un proveedor externo, y separar el dato de su medición hace que
    sea fácil olvidar la segunda.

    `tokens_entrada` y `tokens_salida` pueden ser None: no todos los
    proveedores los reportan, y un cero fingido sería peor que un ausente
    declarado — un cero se suma en los agregados y contamina el costo.
    """

    texto: str
    proveedor: str
    modelo: str
    latencia_ms: float
    tokens_entrada: int | None = None
    tokens_salida: int | None = None


class ProveedorLLM(ABC):
    """Contrato que cumple todo proveedor de lenguaje del sistema.

    La firma separa la instrucción de la entrada **a propósito, y no por
    comodidad**: son dos cosas con distinta confianza. La instrucción la
    escribe el sistema; la entrada viene de una persona de fuera. Un
    adaptador debe llevarlas por canales distintos —rol de sistema y rol de
    usuario— para que el texto del usuario nunca pueda leerse como una orden.

    Si el puerto recibiera un único texto ya concatenado, esa distinción se
    perdería en el dominio y ningún adaptador podría recuperarla.
    """

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador del proveedor para el registro: `groq`, `falso`…"""

    @abstractmethod
    def completar(self, instruccion: str, entrada: str) -> RespuestaLLM:
        """Pide una respuesta al modelo.

        - `instruccion`: qué debe hacer el modelo. La escribe el sistema.
        - `entrada`: el dato sobre el que trabaja. Puede venir de un usuario
          y **se trata siempre como dato, nunca como instrucción**.

        Devuelve `RespuestaLLM` con el texto y su medición.

        La implementación debe ser lo más determinista que el proveedor
        permita: las dos tareas del sistema —clasificar y responder citando
        políticas— buscan reproducibilidad, no variedad. Cómo se consigue
        (temperatura, semilla) es asunto del adaptador; el dominio no conoce
        ese vocabulario.

        Lanza `ProveedorNoDisponible` si no hubo respuesta utilizable tras
        los reintentos, o `RespuestaInutilizable` si respondió algo que no
        se puede leer. Nunca propaga una excepción de la librería de
        transporte.
        """


class Vectorizador(ABC):
    """Contrato de quien convierte texto en vectores comparables.

    Existe por la misma razón que `ProveedorLLM`: la recuperación no debe
    saber si detrás hay un conteo de palabras o un modelo de embeddings
    remoto. Cambiar de uno a otro es cambiar configuración.

    **Los dos métodos no son el mismo con distinto nombre.** Un vectorizador
    que aprende del corpus —TF-IDF necesita saber en cuántos documentos
    aparece cada término— hace ese trabajo en `indexar`, y `consultar` debe
    usar exactamente la representación aprendida allí. Con un solo método
    genérico, quien lo implemente tendría que adivinar cuándo aprender, y
    vectorizar la consulta con un vocabulario distinto del corpus produce
    similitudes que no significan nada.

    Un vectorizador que no aprende —una API de embeddings— implementa los dos
    igual, y eso está bien: el contrato admite ambos sin que el dominio note
    la diferencia.
    """

    @property
    @abstractmethod
    def nombre(self) -> str:
        """Identificador para el registro: `tfidf`, `openai`…"""

    @abstractmethod
    def indexar(self, textos: Sequence[str]) -> list[Vector]:
        """Vectoriza el corpus completo. Aquí aprende, si tiene que aprender."""

    @abstractmethod
    def consultar(self, texto: str) -> Vector:
        """Vectoriza una consulta con la representación del corpus indexado.

        Lanza `RuntimeError` si se llama antes de `indexar` en un vectorizador
        que lo necesita. Devolver un vector con otro vocabulario sería peor:
        produciría similitudes silenciosamente sin sentido.
        """

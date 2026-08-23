"""Idempotencia: repetir una operación no debe repetir su efecto.

El problema no es «evitar duplicados» en abstracto. Es este:

    Cliente ──POST──> API ──crea SOL-000001──> responde
                                                   ✗ se pierde en la red

El cliente no sabe si la solicitud existe. Reintenta, y sin protección se
crea una segunda. El servidor no se equivocó —hizo dos veces lo que le
pidieron dos veces—; lo que falta es que la operación sea repetible sin
efecto.

**Dos identificadores que no son lo mismo.** `SOL-000001` identifica el
recurso creado y lo asigna el servidor. `abc-123` identifica la *intención de
ejecutar una operación* y lo genera el cliente **antes** de intentar nada:
por eso sobrevive al reintento, mientras que el código del recurso no existe
todavía cuando hace falta.

La pieza delicada de todo esto es `reservar`. Preguntar «¿ya existe?» y
después escribir son dos operaciones, y entre las dos cabe otra petición:

    Petición A: ¿existe abc-123? → no
    Petición B: ¿existe abc-123? → no        ← ninguna ha escrito aún
    Petición A: crear                        ← SOL-000001
    Petición B: crear                        ← SOL-000002  💥

Por eso el contrato de `reservar` es **consultar y reservar a la vez**, en
una sola operación indivisible. Un adaptador que lo implemente con dos pasos
cumple la firma y no cumple la garantía. En SQL, esa indivisibilidad la da
una restricción `UNIQUE` sobre la clave; en memoria, un cerrojo.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Los cuatro desenlaces posibles de intentar reservar una clave.
RESERVA_NUEVA = "nueva"
RESERVA_REPETIDA = "repetida"
RESERVA_EN_CURSO = "en_curso"
RESERVA_CONFLICTO = "conflicto"

LARGO_MAXIMO_CLAVE = 128


class ClaveIdempotenciaInvalida(Exception):
    """La clave enviada no es utilizable."""


class ClaveIdempotenciaReutilizada(Exception):
    """La clave ya se usó para una operación con otro contenido.

    Se distingue de una repetición legítima a propósito. Devolver la solicitud
    original sería peor que fallar: el cliente creería que registró su
    petición de vacaciones y lo que existe es una de accesos. Un conflicto
    declarado es recuperable; una confusión silenciosa no.
    """


class OperacionEnCurso(Exception):
    """Otra petición con esta misma clave se está procesando ahora mismo."""


@dataclass(frozen=True)
class Reserva:
    """Qué pasó al intentar reservar una clave.

    - `nueva`: la clave se reservó; hay que ejecutar la operación.
    - `repetida`: ya se completó antes; `codigo` trae el recurso resultante.
    - `en_curso`: otra petición la reservó y todavía no termina.
    - `conflicto`: la clave existe pero con otra huella de contenido.
    """

    estado: str
    codigo: str | None = None


def normalizar_clave(valor: str | None) -> str | None:
    """Devuelve la clave utilizable, o None si no viene.

    Una clave vacía o de solo espacios se trata como ausente: enviar la
    cabecera en blanco es no enviarla. Una clave desmedida se rechaza — sin
    cota, un cliente llena la memoria del servidor con claves que nunca
    volverá a usar.
    """
    if valor is None:
        return None
    limpia = valor.strip()
    if not limpia:
        return None
    if len(limpia) > LARGO_MAXIMO_CLAVE:
        raise ClaveIdempotenciaInvalida(
            f"La clave de idempotencia supera los {LARGO_MAXIMO_CLAVE} caracteres."
        )
    return limpia


def calcular_huella(datos: dict[str, Any]) -> str:
    """Resumen del contenido de la petición, para saber si es la misma.

    `sort_keys=True` es lo que hace que dos serializaciones del mismo objeto
    den la misma huella. Sin eso, un cliente cuyo serializador no garantice
    orden estable perdería la idempotencia sin haber cambiado nada.

    Se usa SHA-256 y no un hash rápido porque la huella se compara para
    decidir si dos operaciones son la misma: una colisión aquí haría que una
    petición distinta se tratara como repetición y el cliente recibiera un
    recurso que no pidió. No es criptografía, pero el costo de equivocarse se
    parece más al de la criptografía que al de una tabla de dispersión.
    """
    canonico = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


class RegistroDeIdempotencia(ABC):
    """Almacén de claves de idempotencia."""

    @abstractmethod
    def reservar(self, clave: str, huella: str) -> Reserva:
        """Consulta y reserva **en una sola operación indivisible**.

        No es una recomendación de eficiencia: es la garantía completa. Una
        implementación que consulte y después escriba deja pasar dos
        peticiones simultáneas y produce el duplicado que esto existe para
        evitar.
        """

    @abstractmethod
    def completar(self, clave: str, codigo: str) -> None:
        """Marca la reserva como terminada y la asocia al recurso creado."""

    @abstractmethod
    def liberar(self, clave: str) -> None:
        """Suelta una reserva cuya operación falló.

        Sin esto, un cliente que envía datos inválidos quema su clave y queda
        atrapado: al corregirlos y reintentar con la misma recibiría un
        conflicto permanente por haberse equivocado una vez.
        """

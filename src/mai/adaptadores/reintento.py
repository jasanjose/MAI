"""Cálculo del tiempo de espera entre reintentos.

Vive aparte porque **dos adaptadores lo necesitan igual**: el cliente del
servicio externo de solicitudes y el adaptador del proveedor de lenguaje. La
matemática del retroceso es la misma; lo que cambia entre ellos es cómo
averiguan que el servicio pidió una espera concreta —una cabecera HTTP en un
caso, el cuerpo del error en el otro— y qué errores merecen reintento.

Por eso aquí solo está la parte pura: recibe números y devuelve un número.
No importa `httpx` ni ninguna otra librería de transporte. Ese es el corte
deliberado: compartir el cálculo sin forzar a los dos adaptadores a compartir
una taxonomía de errores que no tienen en común.
"""

from __future__ import annotations

import random

ESPERA_MAXIMA_S = 20.0


def calcular_espera(
    intento: int,
    espera_base_s: float,
    espera_indicada_s: float | None = None,
    espera_maxima_s: float = ESPERA_MAXIMA_S,
) -> float:
    """Segundos que conviene esperar antes del siguiente intento.

    - `intento` es el número del intento que acaba de fallar, empezando en 1.
    - `espera_indicada_s` es lo que el servicio pidió esperar, si lo dijo
      (`Retry-After` en HTTP). Tiene prioridad sobre el cálculo propio: el
      servicio sabe más que nosotros sobre su propia recuperación.
    - El resultado nunca supera `espera_maxima_s`, incluida la indicada: un
      servicio que pide esperar una hora no puede bloquear el proceso.

    Ante `intento` menor que 1 se comporta como si fuera 1, en vez de calcular
    un exponente negativo y devolver una espera minúscula sin sentido.
    """
    if espera_indicada_s is not None and espera_indicada_s >= 0:
        return min(espera_indicada_s, espera_maxima_s)

    intento_efectivo = max(1, intento)
    espera = espera_base_s * (2 ** (intento_efectivo - 1))

    # Dispersión: si varios clientes fallan a la vez, sin esto reintentarían
    # todos en el mismo instante y volverían a tumbar el servicio justo al
    # recuperarse. Es el problema del rebaño atronador.
    #
    # `bandit` marca esta línea como B311 (generador pseudoaleatorio no apto
    # para criptografía) y hace bien en marcarla. Aquí no aplica: el número
    # solo separa reintentos en el tiempo. Nadie obtiene ventaja
    # prediciéndolo y no protege ningún secreto. La excepción se documenta en
    # el punto de uso, no en un archivo de configuración lejano.
    espera += random.uniform(0, espera_base_s)  # noqa: S311  # nosec B311

    return min(espera, espera_maxima_s)


def leer_retry_after(valor: str | None) -> float | None:
    """Traduce la cabecera `Retry-After` a segundos, o None si no es utilizable.

    La especificación permite dos formas: un número de segundos o una fecha
    HTTP. Aquí solo se acepta la numérica, que es la que envía el servicio
    simulado. Ante cualquier otra cosa —una fecha, texto, un número negativo
    o ausencia— devuelve None y el llamador cae al retroceso calculado.

    Se prefiere ignorar un valor que no se entiende antes que adivinarlo:
    interpretar mal una fecha produciría una espera arbitraria.
    """
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio.isdigit():
        return None
    return float(limpio)

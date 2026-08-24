"""Métricas agregadas del sistema.

Lo que no se mide no se puede sostener ante el negocio ni detectar cuándo se
degrada. Este módulo acumula lo que ya viaja en las respuestas —latencia,
tokens, origen— y lo expone agregado.

## Dónde se recolecta, y por qué ahí

**En la capa HTTP, no en el dominio.** El dominio no sabe que existen
métricas: devuelve objetos que ya traen su medición incorporada, y la capa
que atiende la petición los registra al pasar. Meter un colector en el
`Clasificador` lo ataría a una preocupación que no es suya y obligaría a
pasarlo por el constructor de cada servicio.

El costo de esta elección: un uso del dominio que no pase por la API —un
proceso por lotes, por ejemplo— no queda medido. Se acepta porque hoy toda
entrada es HTTP, y se declara para que quien añada el lote sepa que tiene que
registrar también.

## La memoria está acotada, a propósito

Guardar todas las latencias de la vida del proceso hace crecer la memoria sin
techo, y además **desdibuja el presente**: un p95 calculado sobre un mes tarda
días en reflejar que el sistema se degradó hace una hora. Se conservan las
últimas `MUESTRAS_MAXIMAS` de cada operación. Los contadores —cuántas
llamadas, cuántos tokens— sí son totales, porque son sumas y no distribuciones.
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from dataclasses import dataclass, field

MUESTRAS_MAXIMAS = 1000

PERCENTILES = (50, 95, 99)


def percentil(muestras: list[float], p: int) -> float:
    """Percentil `p` por el método del rango más cercano.

    Se elige este método y no la interpolación porque **devuelve un valor que
    de verdad ocurrió**. Un p95 interpolado es un número que ninguna petición
    tardó, y eso confunde cuando alguien intenta encontrar la petición lenta
    para investigarla.

    Con la lista vacía devuelve 0.0: no hay dato. Es una convención discutible
    —`None` sería más honesto— y se elige 0.0 para que el consumidor no tenga
    que ramificar; el contador de la operación, que sí va aparte, dice si hubo
    muestras.
    """
    if not muestras:
        return 0.0
    ordenadas = sorted(muestras)
    indice = max(0, min(len(ordenadas) - 1, round(p / 100 * len(ordenadas) + 0.5) - 1))
    return round(ordenadas[indice], 2)


@dataclass
class ResumenDeOperacion:
    """Latencias de una operación."""

    cuenta: int
    p50: float
    p95: float
    p99: float


@dataclass
class ColectorDeMetricas:
    """Acumula mediciones. Seguro ante peticiones concurrentes."""

    _latencias: dict[str, deque[float]] = field(default_factory=dict)
    _contadores: Counter[str] = field(default_factory=Counter)
    _cerrojo: threading.RLock = field(default_factory=threading.RLock)

    # ── Registro ────────────────────────────────────────────────────────────

    def registrar_operacion(self, operacion: str, latencia_ms: float) -> None:
        """Una petición atendida, con lo que tardó."""
        with self._cerrojo:
            cola = self._latencias.setdefault(operacion, deque(maxlen=MUESTRAS_MAXIMAS))
            cola.append(latencia_ms)
            self._contadores[f"operacion.{operacion}"] += 1

    def registrar_clasificacion(self, origen: str, motivo: str | None) -> None:
        """Una clasificación, con su origen. `motivo` solo si se degradó."""
        with self._cerrojo:
            self._contadores["clasificacion.total"] += 1
            self._contadores[f"clasificacion.origen.{origen}"] += 1
            if motivo:
                self._contadores[f"clasificacion.motivo.{motivo}"] += 1

    def registrar_consulta(self, origen: str, motivo: str | None) -> None:
        """Una consulta de política, con su origen. `motivo` solo si se abstuvo."""
        with self._cerrojo:
            self._contadores["consulta.total"] += 1
            self._contadores[f"consulta.origen.{origen}"] += 1
            if motivo:
                self._contadores[f"consulta.motivo.{motivo}"] += 1

    def registrar_llamada_llm(
        self,
        proveedor: str | None,
        tokens_entrada: int | None,
        tokens_salida: int | None,
        tokens_razonamiento: int | None = None,
    ) -> None:
        """Una llamada al proveedor, con su consumo si lo reportó.

        Los tokens ausentes **no se cuentan como cero**: se cuentan aparte, en
        `llm.llamadas_sin_tokens`. Sumar ceros haría parecer que el sistema
        consume menos de lo que consume, que es justo la métrica que se usa
        para presupuestar.

        `tokens_razonamiento` **no se suma al total**: ya viene dentro de
        `tokens_salida`. Se acumula aparte porque es lo único que distingue un
        modelo verboso de uno que razona de más, y solo el segundo se arregla
        apagando un ajuste. Es opcional para que un proveedor que no informe el
        desglose no obligue a cambiar a quien llama.
        """
        with self._cerrojo:
            self._contadores["llm.llamadas"] += 1
            if proveedor:
                self._contadores[f"llm.proveedor.{proveedor}"] += 1
            if tokens_entrada is None and tokens_salida is None:
                self._contadores["llm.llamadas_sin_tokens"] += 1
                return
            self._contadores["llm.tokens_entrada"] += tokens_entrada or 0
            self._contadores["llm.tokens_salida"] += tokens_salida or 0
            if tokens_razonamiento:
                self._contadores["llm.tokens_razonamiento"] += tokens_razonamiento

    # ── Lectura ─────────────────────────────────────────────────────────────

    def resumen(self) -> dict:
        """Todo lo acumulado, listo para exponer."""
        with self._cerrojo:
            latencias = {op: list(cola) for op, cola in self._latencias.items()}
            contadores = dict(self._contadores)

        operaciones = {
            operacion: ResumenDeOperacion(
                cuenta=len(muestras),
                p50=percentil(muestras, 50),
                p95=percentil(muestras, 95),
                p99=percentil(muestras, 99),
            ).__dict__
            for operacion, muestras in latencias.items()
        }

        return {
            "operaciones": operaciones,
            "clasificacion": _tasas(contadores, "clasificacion", "degradado"),
            "consultas": _tasas(contadores, "consulta", "abstencion"),
            "proveedor_llm": {
                "llamadas": contadores.get("llm.llamadas", 0),
                "llamadas_sin_tokens_reportados": contadores.get("llm.llamadas_sin_tokens", 0),
                "tokens_entrada": contadores.get("llm.tokens_entrada", 0),
                "tokens_salida": contadores.get("llm.tokens_salida", 0),
                # Subconjunto de tokens_salida, no un sumando aparte. Un valor
                # alto aquí es accionable: se apaga el razonamiento y baja el
                # costo sin tocar el modelo.
                "tokens_razonamiento": contadores.get("llm.tokens_razonamiento", 0),
                "por_proveedor": {
                    clave.removeprefix("llm.proveedor."): valor
                    for clave, valor in contadores.items()
                    if clave.startswith("llm.proveedor.")
                },
                # El costo en dinero NO se estima aquí. Exige el precio por
                # millón de tokens de cada proveedor, que se consulta contra
                # su documentación y no se pone de memoria. Un costo inventado
                # es peor que ninguno: se usaría para presupuestar.
                "costo_estimado": None,
            },
        }


def _tasas(contadores: dict[str, int], prefijo: str, origen_malo: str) -> dict:
    """Cuentas y tasa del origen que interesa vigilar."""
    total = contadores.get(f"{prefijo}.total", 0)
    malos = contadores.get(f"{prefijo}.origen.{origen_malo}", 0)
    return {
        "total": total,
        origen_malo: malos,
        f"tasa_{origen_malo}": round(malos / total, 4) if total else 0.0,
        "por_motivo": {
            clave.removeprefix(f"{prefijo}.motivo."): valor
            for clave, valor in contadores.items()
            if clave.startswith(f"{prefijo}.motivo.")
        },
    }

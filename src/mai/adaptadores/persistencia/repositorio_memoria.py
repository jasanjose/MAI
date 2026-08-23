"""Repositorio de solicitudes en memoria.

Implementa el puerto `RepositorioSolicitudes` guardando todo en un
diccionario del proceso. **Los datos se pierden al reiniciar**, y eso está
declarado como límite en el README y en `docs/decisiones.md` (D-005). Lo que
se gana a cambio: la suite corre sin base de datos, sin red y en
milisegundos, y cambiar a SQL será un adaptador nuevo y no una reescritura.

Lleva un cerrojo. Bajo CPython con GIL la carrera del contador casi nunca se
manifiesta —se midió sin proteger, con 20 hilos y 10.000 códigos, y no
produjo un solo duplicado—, así que el cerrojo no arregla un defecto visible
hoy. Está porque el GIL es un detalle de implementación de CPython y no una
garantía del lenguaje: Python 3.13 ya distribuye compilaciones sin él, y ahí
una lectura seguida de una escritura sobre estado compartido sí se entrelaza.

Un contador de identificadores que depende de un detalle del intérprete para
no duplicar es una bomba con el temporizador puesto en la versión siguiente.
El costo del cerrojo es despreciable; el de un código repetido, no.
"""

from __future__ import annotations

import threading

from mai.dominio.solicitudes import (
    FiltrosDeListado,
    RepositorioSolicitudes,
    Solicitud,
    SolicitudNoEncontrada,
)

PREFIJO_CODIGO = "SOL"
ANCHO_CODIGO = 6


class RepositorioEnMemoria(RepositorioSolicitudes):
    """Almacén de solicitudes en el proceso, seguro ante concurrencia."""

    def __init__(self) -> None:
        self._solicitudes: dict[str, Solicitud] = {}
        self._ultimo_numero = 0
        # Protege el contador y el diccionario. Con `RLock` en vez de `Lock`
        # para que un método que ya lo tenga pueda llamar a otro sin trabarse
        # contra sí mismo.
        self._cerrojo = threading.RLock()

    def siguiente_codigo(self) -> str:
        """Reserva un código. Leer e incrementar es una sola operación.

        Separarlas es lo que produce códigos duplicados bajo concurrencia.
        """
        with self._cerrojo:
            self._ultimo_numero += 1
            return f"{PREFIJO_CODIGO}-{self._ultimo_numero:0{ANCHO_CODIGO}d}"

    def guardar(self, solicitud: Solicitud) -> None:
        with self._cerrojo:
            self._solicitudes[solicitud.codigo] = solicitud

    def obtener(self, codigo: str) -> Solicitud:
        with self._cerrojo:
            solicitud = self._solicitudes.get(codigo)
        if solicitud is None:
            raise SolicitudNoEncontrada(f"No existe la solicitud «{codigo}».")
        return solicitud

    def listar(self, filtros: FiltrosDeListado) -> list[Solicitud]:
        coincidencias = self._coincidencias(filtros)
        desde = filtros.desplazamiento
        return coincidencias[desde : desde + filtros.limite]

    def contar(self, filtros: FiltrosDeListado) -> int:
        return len(self._coincidencias(filtros))

    # ── Interno ─────────────────────────────────────────────────────────────

    def _coincidencias(self, filtros: FiltrosDeListado) -> list[Solicitud]:
        """Las que cumplen los filtros, más recientes primero.

        Se copia la lista dentro del cerrojo y se filtra fuera: sostenerlo
        durante el recorrido bloquearía las escrituras más tiempo del
        necesario.
        """
        with self._cerrojo:
            todas = list(self._solicitudes.values())

        return [s for s in reversed(todas) if self._cumple(s, filtros)]

    @staticmethod
    def _cumple(solicitud: Solicitud, filtros: FiltrosDeListado) -> bool:
        campos = (
            (filtros.area, solicitud.area),
            (filtros.estado, solicitud.estado),
            (filtros.categoria, solicitud.categoria),
            (filtros.prioridad, solicitud.prioridad),
        )
        # Un filtro ausente no filtra. Los valores ya llegan normalizados por
        # el servicio, así que la comparación es exacta a propósito: comparar
        # sin distinguir mayúsculas aquí escondería un fallo de normalización
        # aguas arriba.
        return all(pedido is None or pedido == valor for pedido, valor in campos)

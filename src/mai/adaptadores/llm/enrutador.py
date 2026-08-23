"""Cadena de proveedores con reserva.

El enrutador **es él mismo un `ProveedorLLM`**. Esa es la decisión central de
este archivo: el dominio recibe algo que cumple el puerto y no sabe —ni
necesita saber— si detrás hay un proveedor o cinco encadenados. Cambiar de
«un proveedor» a «una cadena con reserva» no toca una línea del dominio.

La alternativa era que el `Clasificador` recibiera una lista y recorriera los
proveedores él mismo. Se descartó: pondría lógica de infraestructura
—reintentos entre proveedores, orden de preferencia— dentro de una clase de
negocio, y obligaría a repetirla en cada servicio que use un modelo.

**La cadena cruza proveedores distintos a propósito.** Reintentar dentro del
mismo proveedor no es reserva: si el proveedor tiene un incidente, el
segundo intento cae con el primero. Otra empresa es otra red y otra
infraestructura (ADR-004 §C).

**El adaptador falso no pertenece a una cadena de producción.** Si respondiera
cuando todos los reales fallaron, devolvería un texto determinista que parece
real justo en el peor momento, y quien lo recibe no tendría forma de
distinguirlo de una respuesta buena. Cuando la cadena se agota se lanza
`CadenaAgotada`, y es el dominio —que sabe de qué tarea se trata— quien
decide qué significa degradarse.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from mai.dominio.puertos import (
    CadenaAgotada,
    ErrorProveedorLLM,
    ProveedorLLM,
    RespuestaLLM,
)

logger = logging.getLogger(__name__)


class EnrutadorLLM(ProveedorLLM):
    """Prueba los proveedores en orden y devuelve la primera respuesta buena.

    El orden es el de preferencia y lo fija la configuración, no este archivo:
    para clasificar manda la latencia, para responder políticas manda la
    fidelidad (ADR-004 §3).
    """

    def __init__(self, proveedores: Sequence[ProveedorLLM], nombre: str = "cadena") -> None:
        if not proveedores:
            raise ValueError(
                "Una cadena de proveedores no puede estar vacía. Revise "
                "RUTA_CLASIFICACION o RUTA_RAG."
            )
        self._proveedores = list(proveedores)
        self._nombre = nombre

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def proveedores(self) -> tuple[str, ...]:
        """Los eslabones, en orden. Para registro y diagnóstico."""
        return tuple(p.nombre for p in self._proveedores)

    def completar(self, instruccion: str, entrada: str) -> RespuestaLLM:
        """Recorre la cadena. Lanza `CadenaAgotada` si ninguno responde."""
        motivos: list[str] = []

        for posicion, proveedor in enumerate(self._proveedores, start=1):
            try:
                return proveedor.completar(instruccion, entrada)
            except ErrorProveedorLLM as error:
                motivos.append(f"{proveedor.nombre}: {error}")
                # Se registra cada caída con su posición, no solo la última.
                # Que el primario falle a diario y el sistema siga verde
                # gracias a la reserva es información que hay que ver: es la
                # señal de que hay que rehacer la cadena, no de que funciona.
                logger.warning(
                    "proveedor_llm_caido",
                    extra={
                        "proveedor": proveedor.nombre,
                        "posicion_en_cadena": posicion,
                        "quedan_alternativas": posicion < len(self._proveedores),
                    },
                )

        logger.error(
            "cadena_llm_agotada",
            extra={"cadena": list(self.proveedores), "intentados": len(self._proveedores)},
        )
        raise CadenaAgotada(
            "Ningún proveedor de la cadena respondió "
            f"({', '.join(self.proveedores)}). Detalle: {' | '.join(motivos)}"
        )

    def cerrar(self) -> None:
        """Cierra los eslabones que tengan recursos abiertos.

        Se recorre entero aunque uno falle al cerrar: un error cerrando el
        primero no puede dejar los demás sin cerrar.
        """
        for proveedor in self._proveedores:
            cerrar = getattr(proveedor, "cerrar", None)
            if cerrar is None:
                continue
            try:
                cerrar()
            except Exception:  # noqa: BLE001
                logger.warning("fallo_al_cerrar_proveedor", extra={"proveedor": proveedor.nombre})

    def __enter__(self) -> EnrutadorLLM:
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()

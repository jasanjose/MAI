"""Lo que difiere entre proveedores, en un solo sitio.

`AdaptadorCompatible` existe porque cinco proveedores hablan el mismo
protocolo. Pero «el mismo protocolo» no es «la misma petición»: hay ajustes
que cada uno nombra a su manera y que el resto ignora. Ese conocimiento no
cabe en el adaptador —lo volvería específico, que es justo lo que no debe
ser— ni en `enrutador.py`, que resuelve otra cosa: la cadena con reserva.

Vive aquí. **Añadir un proveedor es añadir una línea a `PERFILES`**, y la
prueba de coherencia obliga a documentarlo además en `.env.example`.

## El caso que motivó este archivo: el flag de razonamiento

Se llama distinto en cada proveedor y **el nombre equivocado se ignora en
silencio**: la petición no falla, responde bien, tarde y cara. Es el peor tipo
de fallo que hay, el que no produce ninguna señal.

Se apaga por defecto porque las dos tareas del sistema no lo necesitan.
Clasificar en un catálogo **cerrado** de 12 categorías no es un problema de
razonamiento: añade latencia y tokens de salida sin mejorar la precisión, y los
de salida son los caros. Ver `docs/costos.md`. Si algún día una tarea sí lo
necesitara, se enciende aquí y en un solo sitio.

## Cómo se verifica que quedó apagado

**Por efecto, nunca por campo.** Comprobar que el diccionario contiene
`enable_thinking: False` da verde con la versión rota, porque el problema no
es que no se envíe: es que el proveedor no lo mira. Lo que hay que mirar es
la respuesta — `tokens_razonamiento` en cero.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PerfilProveedor:
    """Configuración propia de un proveedor compatible con Chat Completions."""

    prefijo_entorno: str
    ajustes: Mapping[str, object] = field(default_factory=dict)

    def cuerpo_extra(self) -> dict[str, object]:
        """Copia nueva de los ajustes, lista para fusionar en la petición.

        Devuelve una **copia profunda** y no la tabla, a propósito. Si quien
        la recibe mutara el diccionario devuelto —o algo anidado dentro—,
        estaría alterando la configuración de todas las llamadas siguientes
        del proceso. Es el mismo defecto que el argumento mutable por defecto
        del módulo heredado (S2), y se previene igual: no compartir el objeto.

        Con un proveedor sin ajustes devuelve `{}`, que fusionado no cambia
        nada: el cuerpo sale idéntico al que se enviaba antes de este archivo.
        """
        return copy.deepcopy(dict(self.ajustes))


# Apagar el razonamiento. Cada proveedor lo nombra distinto y el ajeno se
# ignora sin avisar; por eso la tabla, y no una constante compartida.
_SIN_RAZONAMIENTO_ALIBABA = {"enable_thinking": False}
_SIN_RAZONAMIENTO_OPENROUTER = {"reasoning": {"enabled": False}}


PERFILES: dict[str, PerfilProveedor] = {
    "groq": PerfilProveedor("GROQ"),
    "dashscope": PerfilProveedor("DASHSCOPE", _SIN_RAZONAMIENTO_ALIBABA),
    "openai": PerfilProveedor("OPENAI"),
    "openrouter": PerfilProveedor("OPENROUTER", _SIN_RAZONAMIENTO_OPENROUTER),
    "gemini": PerfilProveedor("GEMINI"),
    "ollama": PerfilProveedor("OLLAMA"),
}


def perfil_de(nombre: str) -> PerfilProveedor | None:
    """Perfil del proveedor, o None si no está en la tabla."""
    return PERFILES.get(nombre.strip().lower())

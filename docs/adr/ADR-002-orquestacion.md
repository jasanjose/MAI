# ADR-002 · Orquestación del flujo y contrato con el modelo

**Fecha:** 21 de agosto de 2026 · **Estado:** aceptada
**Decide:** cómo se encadenan los pasos del flujo y cómo se obtiene una
salida estructurada del modelo.

---

## Contexto

El flujo objetivo de la Mesa de Ayuda tiene cuatro pasos:

```
recibir solicitud → clasificar → consultar RAG → redactar respuesta
                                     ↓
                       escalar a una persona si la confianza es baja
```

Es una **secuencia lineal con una bifurcación condicional**. No tiene
ciclos, ni ramas paralelas que después se unan, ni pausas a la espera de
intervención humana dentro de la misma ejecución.

Los tres caminos disponibles son un motor visual tipo n8n, un framework de
agentes, o implementación propia. Ninguno es incorrecto de partida: lo que
decide es qué forma tiene el flujo que hay que orquestar.

Hay una restricción que pesa sobre todo lo demás: **la autoría es
eliminatoria.** Tres fragmentos del código se explican línea por línea y se
modifican en vivo. Toda complejidad que se adopte hay que poder defenderla.

---

## Alternativas consideradas

### 1 · Orquestación

| Opción | A favor | En contra |
|---|---|---|
| **Código propio** | El flujo es lineal con una condición: son ~80 líneas de una función secuencial. Se prueba con `pytest` sin infraestructura. Cero dependencias nuevas. Se explica y se modifica en vivo sin fricción | Si el flujo crece a ciclos, reintentos con estado o pausas, habría que reescribirlo |
| **LangGraph** | Estándar para flujos con estado; da grafo explícito, enrutamiento condicional y puntos de control. Ya se usa en producción en otro proyecto propio, así que hay experiencia real | Introduce nodos, aristas, reductores de estado y *checkpointers* para un flujo de cuatro pasos sin ciclos. Dependencia pesada. En una defensa en vivo hay que explicar el modelo de grafo antes de llegar a la lógica del negocio |
| **n8n** | Muy rápido para cablear webhooks y disparos programados. Visual, legible para alguien no técnico | Es **otro runtime que hay que desplegar y operar**. La lógica vive en un JSON gestionado por una interfaz: no se prueba con `pytest`, no se revisa en un diff y no se explica línea por línea. Para una prueba que evalúa código propio, mueve la lógica fuera de lo evaluable |

### 2 · Cómo se obtiene la salida estructurada del modelo

| Opción | A favor | En contra |
|---|---|---|
| **JSON pedido en el prompt + validación contra catálogo cerrado** | Uniforme en los cuatro proveedores de la cadena. La validación contra las 12 categorías **es obligatoria de todos modos** antes de que la salida toque la base de datos | Un modelo débil puede devolver JSON malformado; hay que manejar ese caso explícitamente |
| **Tool calling / function calling** | Mejor adherencia al esquema en modelos que lo soportan bien | El comportamiento **no es uniforme entre proveedores**, y la cadena de reserva cruza proveedores a propósito. Evidencia propia medida en otro proyecto: en un modelo Qwen, temperatura por encima de 0,5 rompe el esquema en function calling cerca del 25 % de las veces. Además **no elimina la validación**: la añade encima |

---

## Decisión

**1 · Orquestación en código propio.** Una función secuencial explícita con
una bifurcación por confianza. Sin framework de agentes y sin n8n.

**2 · Salida estructurada por JSON en el prompt, validada contra el catálogo
cerrado de 12 categorías.** Sin tool calling.

**3 · Se descarta LangGraph a pesar de tener experiencia con él.** Es la
parte deliberada de esta decisión: la herramienta se dimensiona al problema,
no al currículum. Un grafo de estado para una secuencia de cuatro pasos sin
ciclos añade vocabulario que hay que explicar antes de llegar a lo que el
sistema realmente hace.

**4 · n8n se reconoce como la opción razonable para R-03 en un entorno real.**
El recordatorio de tickets sin gestión —disparo a las 8:00 a. m., plantilla
fija, control de duplicados— es exactamente lo que n8n resuelve bien, y
decirlo importa más que descartarlo por principio. No se usa aquí porque en
esta entrega la lógica debe ser código versionado, probado y defendible.

---

## Consecuencias negativas aceptadas

- **El orquestador propio no trae puntos de control ni reanudación.** Si una
  ejecución falla a mitad de camino, se repite completa. A este volumen es
  aceptable; a volumen alto sería desperdicio.
- **No hay visualización del flujo.** Nadie fuera del equipo técnico puede
  leer el grafo. Se compensa con el diagrama de `docs/arquitectura.md`, que
  hay que mantener a mano y puede quedar desactualizado respecto al código.
- **Sin tool calling se paga con manejo de errores.** Habrá que tratar
  explícitamente el JSON malformado, con reintento y caída a modo degradado.
  Es código adicional que un esquema forzado habría evitado en parte.
- **Migrar después cuesta.** Si el flujo evoluciona a ciclos o a pausas con
  intervención humana, adoptar LangGraph entonces implica reescribir la
  orquestación, no envolverla.

---

## Bajo qué condición se revisaría

Cualquiera de estas la reabre:

1. **El flujo deja de ser lineal**: aparecen ciclos, reintentos que dependen
   del estado acumulado, o ramas paralelas que se unen. Ahí un grafo deja de
   ser vocabulario extra y pasa a ser la estructura correcta.
2. **Se necesita intervención humana dentro de la ejecución** —que un
   analista apruebe antes de continuar, sin perder el estado. Es el caso que
   LangGraph resuelve y el código propio no.
3. **La cadena de proveedores se reduce a uno solo** con tool calling
   estable y medido. Desaparece el argumento de uniformidad y el esquema
   forzado pasa a ser mejor opción que el JSON en el prompt.
4. **El número de flujos pasa de uno a varios** y empiezan a compartir pasos.
   La duplicación entre orquestadores propios se vuelve más cara que adoptar
   un framework.
5. **Operaciones necesita editar el flujo sin tocar código.** Ese es el
   argumento real de n8n, y si aparece, gana.

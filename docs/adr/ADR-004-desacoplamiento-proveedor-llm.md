# ADR-004 · Desacoplamiento del proveedor de IA y cadena de reserva

**Fecha:** 21 de agosto de 2026 · **Estado:** aceptada
**Decide:** cómo se abstrae el proveedor de lenguaje, cómo se conmuta entre
proveedores y qué hace el sistema cuando ninguno responde.

> Los ADR [001](ADR-001-vectorizacion-e-indice.md) (vectorización, índice y
> métrica) y [003](ADR-003-fragmentacion.md) (fragmentación) se escribieron al
> construir el componente RAG.

---

## Contexto

La solución llama a un modelo de lenguaje en dos puntos: **clasificar** una
solicitud en texto libre, y **redactar** la respuesta a una consulta de
política sobre los fragmentos recuperados.

Tres hechos condicionan el diseño:

**1 · No hay una credencial única y estable.** El acceso al proveedor
previsto no llegó. Se usan proveedores propios, incluida la posibilidad de un
modelo local, y la elección se declara con su criterio en este mismo
documento.

**2 · Las dos tareas tienen restricciones opuestas.** R-01 son 3.000
clasificaciones diarias en lote, donde el error se corrige en menos de un
minuto y no afecta al usuario: mandan latencia y costo. R-02 son 80
consultas diarias donde una respuesta equivocada sobre montos o plazos
genera reclamación formal ante Talento Humano: manda la fidelidad.

**3 · La integración continua no puede depender de una credencial.** Las
pruebas tienen que correr sin red y de forma reproducible.

Y sobre todo esto pesa el criterio de aceptación que fija `CLAUDE.md` §3:
*«cambiar de proveedor debe ser cambiar la variable de entorno. Cero líneas
de código. Si hay que tocar el dominio, el diseño está mal.»*

---

## Alternativas consideradas

### A · Cómo se abstrae el proveedor

| Opción | A favor | En contra |
|---|---|---|
| **Puerto en el dominio + adaptadores** | El dominio depende de una interfaz, nunca de un proveedor. Cambiar de modelo es cambiar una variable de entorno. Permite un adaptador falso determinista para CI | Una capa de indirección más que hay que sostener y explicar |
| Llamada directa al SDK del proveedor | Menos código, menos capas | Acopla la lógica de negocio al proveedor: cambiar de modelo obliga a tocar el dominio. Y hace imposible correr las pruebas sin credencial |
| Un enrutador tipo `litellm` o similar | Resuelve la conmutación entre proveedores sin escribirla | Dependencia grande para un problema pequeño. La lógica de conmutación —cadena, degradado, medición— es el núcleo de esta decisión, y quedaría dentro de una caja que hay que entender igual para operarla |

### B · Cuántos adaptadores concretos

| Opción | A favor | En contra |
|---|---|---|
| **Uno solo, `openai_compatible`** | OpenAI, Groq, DashScope, OpenRouter y Ollama hablan todos Chat Completions: cambian `base_url`, `api_key` y `model`. Cinco proveedores con un archivo y una sola ruta de error que probar | Deja fuera a los que no siguen esa forma, como Anthropic |
| Uno por proveedor | Más fiel a las particularidades de cada API | Cinco archivos casi idénticos. Cinco veces la misma lógica de timeout, reintento y medición — y cinco superficies distintas que mantener y probar |

### C · Qué hacer cuando el proveedor primario falla

| Opción | A favor | En contra |
|---|---|---|
| **Cadena que cruza proveedores** | Un fallo de un proveedor no arrastra al siguiente: otra empresa, otra red, otra infraestructura | Hay que normalizar diferencias de comportamiento entre modelos distintos |
| Reintentar en el mismo proveedor | Simple, y el modelo no cambia entre intentos | Un incidente del proveedor deja al sistema sin salida. Un «fallback» dentro del mismo vendedor se cae junto con el primario: no es reserva, es esperar |
| Sin reserva, solo error | El más simple | Propaga una excepción cruda al usuario ante un fallo ajeno. `CLAUDE.md` §3 lo prohíbe |

### D · Qué es el último recurso

| Opción | A favor | En contra |
|---|---|---|
| **Modo degradado explícito y marcado** | El sistema responde algo útil y **declara** que viene de la ruta alterna, con `origen: "degradado"` y `confianza: "baja"`. Quien lo consume puede decidir | Hay que escribir y mantener la ruta alterna |
| El adaptador falso como último eslabón | Reutiliza código que ya existe para CI | **Devolvería una respuesta determinista que parece real justo cuando todo lo demás falló.** El usuario no tendría forma de distinguirla de una buena. Es peor que fallar |
| Fallar y ya | Honesto | Para clasificar es desperdicio: una regla por palabras clave acierta lo suficiente en un problema cuyo error cuesta un minuto |

---

## Decisión

**1 · Puerto en el dominio, adaptadores en infraestructura.**
`dominio/puertos.py` define `ProveedorLLM`. El dominio nunca importa un
proveedor concreto. La fábrica lee la configuración y arma la cadena.

**2 · Un solo adaptador concreto, `openai_compatible`**, parametrizado por
`base_url`, `api_key` y `model`. Cubre Groq, DashScope, OpenAI, OpenRouter y
Ollama. **Anthropic queda fuera**: no habla Chat Completions y exigiría un
segundo adaptador cuyo costo no se justifica en este alcance. Si hiciera
falta, entra vía OpenRouter.

**3 · Dos rutas, porque las dos tareas tienen restricciones opuestas:**

```
RUTA_CLASIFICACION=groq,dashscope     # manda latencia y costo
RUTA_RAG=openai,dashscope             # manda fidelidad
RUTA_*=falso                          # en CI: sin red, sin credenciales
```

Groq encabeza clasificación por velocidad. Su límite de tasa agresivo —429
con `Retry-After`— no es un inconveniente sino una ventaja: obliga a que el
manejo de reintentos sea código real y probado, el mismo que exige el
servicio mock. OpenAI encabeza RAG porque lo que se rompe en abstención es
la complacencia del modelo ante «responde solo con estos fragmentos».

**4 · `falso` no pertenece a la cadena de producción.** Es un adaptador de
pruebas y se selecciona como cadena completa en CI. Cuando la cadena real se
agota, entra el modo degradado.

**5 · El modo degradado es distinto según la tarea.** Esta es la parte que
no se hereda de ningún framework:

| Tarea | Degradado | Por qué |
|---|---|---|
| Clasificar | Reglas por palabras clave sobre el catálogo cerrado, con `origen: "degradado"` y `confianza: "baja"` | El error cuesta un minuto de un analista. Una clasificación aproximada y marcada es mejor que ninguna |
| Responder política | **Abstención y escalamiento a persona.** Nunca reglas | R-02 dice que un error genera reclamación formal. Responder por reglas cuando no hay proveedor es inventar sin evidencia, que es justo lo que `CLAUDE.md` §8 prohíbe |

**6 · Todo adaptador implementa, sin excepción:** tiempo de espera explícito,
reintento con retroceso exponencial respetando `Retry-After`, y reporte de
`latencia_ms`, `tokens_entrada`, `tokens_salida`, `costo_estimado`,
`proveedor`, `modelo` y `resultado`.

**7 · La salida del modelo se valida contra el catálogo cerrado de 12
categorías antes de tocar nada persistente.** Un modelo que devuelve
«Hardware/Software» o una categoría inventada produce un rechazo, no un
registro.

---

## Consecuencias negativas aceptadas

- **Anthropic no es utilizable directamente**, aunque haya credencial
  disponible. Se renuncia a un modelo de buena calidad por no pagar un
  segundo adaptador.
- **La cadena cruza modelos distintos, y modelos distintos redactan
  distinto.** La respuesta a la misma pregunta no es idéntica según qué
  eslabón la atendió. Se mitiga con validación de salida, pero no
  desaparece: es el precio de tener reserva real.
- **Dos rutas es más configuración que una.** Alguien puede dejarlas
  inconsistentes entre ambientes. Se mitiga documentándolas en
  `.env.example`, no eliminándolas.
- **El modo degradado por reglas envejece.** Es una lista de palabras clave
  que hay que mantener cuando el catálogo cambie, y nadie se acuerda de
  mantener el camino que casi nunca se ejecuta.
- **Medir en cada llamada tiene costo.** Latencia y tokens en cada petición
  añaden trabajo y volumen de registro. Se acepta porque sin medición no se
  puede sostener el sistema ante el negocio ni detectar cuándo se degrada.
- **La abstracción se pagó por adelantado.** Hoy hay dos tareas y cuatro
  proveedores posibles; con un solo proveedor fijo, el puerto sería
  ceremonia. Se acepta porque el criterio evaluado es exactamente ese, y
  porque no hay proveedor fijo garantizado.

---

## Bajo qué condición se revisaría

1. **Llega una credencial corporativa única y estable con acuerdo de
   servicio.** Desaparece el argumento de la reserva entre proveedores y la
   cadena podría reducirse a uno con reintento local.
2. **Un proveedor de la cadena deja de hablar Chat Completions**, o se
   necesita uno que nunca lo habló. Vuelve la discusión del adaptador por
   proveedor.
3. **El modo degradado empieza a ejecutarse con frecuencia medible.** Si
   deja de ser excepción, el problema no es la ruta alterna sino la elección
   del primario, y hay que rehacer la cadena.
4. **Las dos tareas convergen en la misma restricción** —por ejemplo, si la
   clasificación pasa de lote horario a tiempo real con costo de error alto.
   Dos rutas dejarían de justificarse.
5. **Aparece un tercer punto de llamada al modelo.** Con tres tareas, la
   configuración por variables sueltas se vuelve frágil y toca pasar a
   configuración declarativa por tarea.
6. **El volumen crece hasta que el costo de medir sea significativo frente
   al de inferir.** Entonces se muestrea en vez de medir todo.

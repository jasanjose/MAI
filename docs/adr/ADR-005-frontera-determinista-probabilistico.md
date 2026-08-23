# ADR-005 · Frontera entre lo determinista y lo probabilístico

**Fecha:** 21 de agosto de 2026 · **Estado:** aceptada
**Decide:** qué partes del sistema resuelve una regla, cuáles un modelo de
lenguaje, y qué pasa en la frontera cuando ninguno de los dos alcanza.

---

## Contexto

Es fácil caer en uno de dos extremos. Uno es meter un modelo de lenguaje en
todas partes porque el proyecto se llama «inteligente». El otro es evitarlo
por desconfianza y escribir reglas para problemas que no se pueden enumerar.

Los dos producen sistemas malos, y por el mismo motivo: **eligen la
herramienta antes de mirar el problema.**

El sistema tiene tres decisiones de naturaleza distinta:

- **Normalizar el histórico.** 58 formas de escribir 12 categorías. El
  espacio de entrada es finito y conocido.
- **Clasificar una solicitud en texto libre.** 3.000 diarias, escritas por
  personas. El espacio de entrada es infinito.
- **Recordar un ticket sin gestión.** Regla de tres días hábiles, plantilla
  fija, disparo a las 8:00 a. m., prohibido duplicar.

Tratarlas igual sería el error.

---

## Alternativas consideradas

| Opción | A favor | En contra |
|---|---|---|
| **Regla primero; el modelo solo en el residuo, y solo si el error es barato** ✅ | Cada decisión usa la herramienta que le corresponde. Lo reproducible se mantiene reproducible. Se paga por inferencia únicamente donde la regla no puede llegar | Hay que sostener dos caminos y decidir explícitamente cuál va primero en cada punto |
| Modelo de lenguaje en todo el flujo | Un solo mecanismo, menos código de reglas | Rompe la reproducibilidad de un proceso por lotes: la misma entrada deja de producir la misma salida y el reporte de calidad pierde sentido. Cuesta por fila con 3.000 diarias. No es más preciso donde el mapeo ya se conoce |
| Reglas en todo | Barato, reproducible, auditable | Imposible para texto libre: no se enumera lo que un usuario puede escribir. Obligaría a mantener listas de palabras clave que envejecen mal |
| Modelo como respaldo automático de **toda** regla que falle | Ninguna entrada se queda sin respuesta | **Es la opción peligrosa.** Convierte fallos ruidosos en respuestas plausibles. Un modelo que adivina una fecha ilegible corrompe un informe en silencio, y nadie se entera |

---

## Decisión

### Criterio 1 — quién va primero: ¿el espacio de entrada es enumerable?

| El espacio es… | Primero | El otro es… |
|---|---|---|
| **Enumerable** — catálogo cerrado, variantes de escritura conocidas | La **regla** | El modelo, solo sobre el residuo |
| **No enumerable** — texto libre escrito por una persona | El **modelo** | La regla, como modo degradado |

Esto explica una asimetría que de otro modo parecería incoherente: en la
etapa 1 la regla va primero y en la etapa 2 va primero el modelo. No es
inconsistencia; es que **el espacio de entrada cambió**.

### Criterio 2 — si la primera opción no resuelve, ¿puede entrar la otra?

No siempre. Depende de qué cuesta equivocarse:

> **¿El error sería detectable y barato? → puede entrar el modelo.
> ¿Sería silencioso o caro? → cuarentena o abstención.**

Este criterio no es una preferencia: sale de los requerimientos del negocio.
R-01 dice que una clasificación errada se corrige en menos de un minuto y no
afecta al usuario. R-02 dice que una respuesta equivocada sobre montos o
plazos genera reclamación formal. Son costos de error de órdenes distintos y
merecen políticas distintas.

### Aplicación punto por punto

| Decisión | Primero | ¿Entra el modelo en el residuo? | Por qué |
|---|---|---|---|
| Normalizar categoría, prioridad, estado, canal | Regla | **Sí.** Un valor fuera de catálogo lo resuelve el modelo eligiendo entre las 12, marcado `origen: "inferido"`, `confianza: media` | El error es visible y cuesta un minuto corregirlo |
| Normalizar fechas | Regla | **No. Nunca.** Un formato desconocido va a cuarentena y ahí se queda | Un modelo que interpreta `03/04/25` puede devolver marzo o abril. La fecha equivocada no se ve: contamina el informe en silencio |
| Detectar duplicados | Regla | **No** | Comparación exacta tras normalizar. No hay ambigüedad que resolver |
| Clasificar texto libre (R-01) | **Modelo** | La regla por palabras clave es el degradado, marcado `confianza: baja` | El espacio no se enumera. Es el terreno propio del modelo |
| Responder consulta de política (R-02) | **Modelo** con recuperación | **Abstención.** Sin evidencia no se responde, se escala | El costo del error es una reclamación formal |
| Recordatorio de tickets (R-03) | **Regla, y solo regla** | **No** | Plantilla fija, disparo programado, exige idempotencia. Un modelo añade costo, latencia y no determinismo a un proceso que exige lo contrario |

### La cuarentena es la cola de entrada del modelo

Consecuencia de diseño que vale la pena nombrar: cada registro apartado
lleva un **motivo tipado**. Ese motivo es lo que autoriza o prohíbe una
segunda pasada probabilística:

```
categoria_fuera_de_catalogo    → elegible para segunda pasada
valor_fuera_de_catalogo        → elegible
fecha_creacion_invalida        → NUNCA elegible
cierre_anterior_a_creacion     → NUNCA elegible
```

La cuarentena deja de ser un basurero y pasa a ser una cola tipada. El
acoplamiento ya existe en el código: no hubo que añadir nada.

### Qué NO se implementa todavía

La segunda pasada con modelo **no se construye en la etapa 1**, por dos
razones:

1. El pipeline de limpieza debe correr en integración continua **sin red y
   sin credenciales**. Meterle una dependencia de proveedor lo rompería.
2. Sobre los 2.000 registros del histórico, la segunda pasada procesaría
   **exactamente cero registros**: no hay ni un valor fuera de catálogo.
   Construirla hoy sería código para un caso que no ocurre.

Se implementa en la etapa 2, donde el adaptador de proveedor ya existe y
donde hay trabajo real: la clasificación de texto libre.

---

## Consecuencias negativas aceptadas

- **Hay dos caminos que mantener**, y la frontera entre ellos hay que
  revisarla cada vez que se añade una decisión al sistema. Un solo mecanismo
  sería más simple de operar.
- **Las reglas de normalización envejecen.** Cuando el negocio agregue una
  categoría, alguien tiene que tocar el mapa y desplegarlo. Un modelo se
  habría adaptado solo — a cambio de no ser reproducible.
- **La cuarentena de fechas nunca se vacía sola.** Requiere intervención
  humana por diseño. Es el costo consciente de no adivinar.
- **Marcar `origen` y `confianza` obliga a que todo consumidor los mire.**
  Un consumidor que ignore esos campos trata una inferencia como un hecho, y
  el sistema no puede impedirlo desde aquí.
- **La segunda pasada queda diseñada pero no probada** hasta la etapa 2. Es
  deuda declarada, no capacidad entregada.

---

## Bajo qué condición se revisaría

1. **El catálogo de 12 categorías deja de ser estable.** R-01 dice que no ha
   cambiado en tres años; si empieza a mutar o aparecen clases sin histórico,
   la regla deja de ser la opción barata y el modelo pasa a primera línea.
2. **La cuarentena por valor fuera de catálogo crece de forma sostenida.** Si
   deja de ser residuo, la regla está mal calibrada y hay que rehacer el
   mapa, no compensarlo con inferencia.
3. **Aparece un modelo con salida verificable contra la fuente para fechas** —
   por ejemplo, que devuelva el formato detectado y no solo la fecha, de modo
   que la respuesta se pueda comprobar. Entonces el argumento del error
   silencioso deja de aplicar y la prohibición se revisa.
4. **El costo del error de clasificación sube.** Si la categoría empieza a
   disparar un flujo automático con efecto sobre el usuario, deja de ser
   barata y la política de inferencia debe endurecerse.
5. **El volumen de inferencia hace que el costo pese** frente al de mantener
   reglas. Entonces conviene mover al lado determinista todo lo que se pueda
   enumerar.

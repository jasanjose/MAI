# Documento de decisión · R-01, R-02 y R-03

Para cada requerimiento: si la solución es **inteligencia artificial**,
**automatización tradicional** o una **combinación**, con qué criterios,
qué cuesta, qué riesgo tiene y **bajo qué condición cambiaría la decisión**.

| | Requerimiento | Decisión |
|---|---|---|
| **R-01** | Clasificar 3.000 solicitudes diarias en 12 categorías | **Combinación** — ML clásico como motor, IA como excepción |
| **R-02** | Responder consultas de política en lenguaje natural | **IA (RAG)**, con abstención y cita obligatorias |
| **R-03** | Recordatorio a 3 días hábiles, texto fijo, 8:00 a. m. | **Automatización tradicional. La IA es la peor opción** |

---

## Los criterios, antes de aplicarlos

Se fijan primero para que la decisión no se acomode al resultado:

**Volumen.** Más volumen favorece amortizar una inversión de entrenamiento y
castiga el costo por llamada.

**Estabilidad del problema.** Un problema que no cambia se puede aprender una
vez. Uno que cambia cada semana obliga a reentrenar o a razonar en el momento.

**Costo del error.** No cuánto se equivoca, sino **cuánto cuesta cada
equivocación**. Es el criterio que más pesa y el que más se ignora.

**Latencia exigida.** Si nadie espera la respuesta, la latencia no es una
restricción y deja de justificar pagar por velocidad.

**Determinismo exigido.** Si el proceso debe dar exactamente el mismo
resultado ante la misma entrada, un modelo probabilístico es un defecto, no
una funcionalidad.

**Esfuerzo de mantenimiento.** Qué hay que hacer para que siga funcionando
dentro de un año.

---

## R-01 · Clasificación de solicitudes

> 3.000 diarias · 12 categorías estables desde hace tres años · histórico
> etiquetado a mano · el error se corrige en menos de un minuto y no afecta al
> usuario final · **corre en lote cada hora**

### Cómo puntúa

| Criterio | Lectura |
|---|---|
| Volumen | **Muy alto.** 3.000/día son 90.000/mes. El costo por llamada se multiplica por 90.000 |
| Estabilidad | **Alta.** Doce categorías sin cambios en tres años |
| Costo del error | **Bajo.** Un minuto de un analista, sin efecto en el usuario |
| Latencia | **Ninguna.** Lote horario, explícito en el requerimiento |
| Determinismo | Deseable para poder evaluar, no exigido |
| Mantenimiento | Reentrenar cuando cambie el catálogo, que lleva tres años sin cambiar |

**Cuatro de seis apuntan al mismo sitio.** Volumen alto, problema estable,
error barato, sin exigencia de latencia, y —lo decisivo— **existe un histórico
etiquetado a mano**. Es la definición de libro de un clasificador supervisado.

### La decisión, y el matiz que importa

**Motor: ML clásico.** TF-IDF sobre asunto y descripción con un clasificador
lineal, entrenado sobre el histórico. Es lo que resuelve el 100 % del volumen
a costo marginal cero.

**La IA entra solo como excepción**, y por eso es *combinación* y no
«automatización tradicional» a secas: cuando el clasificador reporta baja
confianza —un texto ambiguo, una categoría rara, vocabulario nuevo— esa
fracción se envía al modelo de lenguaje. Con un 5 % de casos dudosos son 150
llamadas diarias en vez de 3.000: **un vigésimo del costo**, aplicado justo
donde el clasificador barato no sirve.

### Costo comparado

| | Llamadas/mes | Costo variable | Costo fijo |
|---|---:|---|---|
| Solo LLM | 90.000 | ~24 M tokens/mes | ninguno |
| **Combinación** | **4.500** | ~1,2 M tokens/mes | entrenamiento inicial + reentrenar |
| Solo clásico | 0 | ninguno | igual, y sin salida para los casos raros |

La combinación cuesta **una vigésima parte** del volumen de tokens y conserva
una respuesta razonable para lo que el clasificador no sabe.

### Riesgo

**Deriva silenciosa.** Un clasificador entrenado sobre el histórico degrada
cuando el vocabulario cambia —un sistema nuevo, un proveedor nuevo— y **no
avisa**: sigue clasificando, peor. Se mitiga midiendo la precisión contra el
conjunto de referencia de forma periódica, no observando la tasa de error, que
nadie mira.

### Bajo qué condición cambiaría

1. **El catálogo pasa a cambiar con frecuencia.** Reentrenar cada semana
   invierte la comparación: un modelo de lenguaje absorbe una categoría nueva
   con una línea de prompt.
2. **El error deja de ser barato.** Si la categoría empieza a disparar
   acciones automáticas —cerrar, escalar, notificar— el costo del error sube y
   conviene pagar por acertar más.
3. **La clasificación pasa a tiempo real con volumen bajo.** Sin lote y con
   pocos casos, el costo fijo del entrenamiento deja de amortizarse.
4. **El histórico deja de ser representativo.** Sin datos etiquetados
   utilizables, el argumento principal desaparece.

---

## R-02 · Consulta de políticas en lenguaje natural

> 80 consultas diarias · las políticas cambian una o dos veces al año · cinco
> PDF · **una respuesta equivocada sobre montos o plazos genera reclamación
> formal ante Talento Humano** · hoy consume el 18 % del tiempo del equipo

### Cómo puntúa

| Criterio | Lectura |
|---|---|
| Volumen | **Bajo.** 80/día son 2.400/mes |
| Estabilidad | Del corpus, alta. **De las preguntas, ninguna**: lenguaje natural abierto |
| Costo del error | **Alto.** Reclamación formal |
| Latencia | Interactiva: alguien espera |
| Determinismo | Deseable, no alcanzable con lenguaje natural abierto |
| Mantenimiento | Reindexar cuando cambie una política. Una o dos veces al año |

### La decisión

**IA con recuperación aumentada.** Es el caso donde la IA es genuinamente la
mejor herramienta: la entrada es lenguaje natural sin forma previsible, y no
hay manera de enumerar las preguntas por adelantado.

Una alternativa determinista —un buscador por palabras clave sobre los PDF—
devolvería el documento, no la respuesta, y dejaría al colaborador leyendo dos
páginas para encontrar una cifra. Eso no recupera el 18 % del tiempo del
equipo: lo traslada al colaborador.

### Pero el costo del error cambia el diseño, no la herramienta

**Aquí está el criterio que importa.** Que la IA sea la herramienta correcta
no significa que baste con usarla. Con reclamación formal como costo del
error, tres cosas dejan de ser opcionales:

**1 · Citar siempre.** Una respuesta sin cita no se emite. El usuario no puede
distinguir una respuesta inventada de una correcta —suenan igual— y la cita es
lo que le devuelve esa capacidad.

**2 · Abstenerse ante evidencia insuficiente.** Inventar una respuesta
plausible es peor que no responder.

**3 · Verificar la cita contra los fragmentos entregados.** Porque el control
2 sin el 3 deja pasar el caso peligroso: respuestas que suenan bien **y traen
cita**, pero la cita se compuso.

Está medido y documentado en
[`calibracion_umbral.md`](calibracion_umbral.md): **ningún umbral de
similitud cumple la abstención del 100 %**. Una pregunta sobre viáticos a
Ciudad de México —que el corpus no cubre— puntúa más alto que 18 de las 21
consultas legítimas, porque léxicamente sí se parece. Eso convierte la
verificación de cita en un control **portante**, no en un refuerzo.

### Costo

2.400 consultas al mes con ~1.000 tokens de entrada son ~2,4 M tokens/mes.
Contra el 18 % del tiempo de un equipo de mesa de ayuda, la comparación no
está cerca. **El riesgo no es el costo: es responder mal.**

### Bajo qué condición cambiaría

1. **Las preguntas resultan ser repetitivas.** Si veinte preguntas cubren el
   80 %, un árbol de respuestas fijas las atiende gratis y con determinismo, y
   el RAG queda para la cola.
2. **La tasa de abstención se estabiliza por encima del 25 %.** Deja de
   ahorrar tiempo y hay que ampliar el corpus, no tolerar el escalamiento.
3. **El corpus crece a cientos de documentos.** Sigue siendo RAG, pero las
   decisiones de ADR-001 y ADR-003 caducan.
4. **Aparece obligación legal de trazabilidad completa.** Habría que
   registrar los fragmentos recuperados y el prompt de cada respuesta, lo que
   choca con no registrar contenido de consultas.

---

## R-03 · Recordatorio de tickets sin gestión

> Tres días hábiles sin cambio de estado → recordatorio al responsable · al
> quinto día, escalamiento al coordinador · **el texto es siempre el mismo**,
> con el código y el nombre · todos los días a las 8:00 a. m. · **no puede
> duplicar si el proceso se ejecuta dos veces**

### Cómo puntúa

| Criterio | Lectura |
|---|---|
| Volumen | Irrelevante: es un lote |
| Estabilidad | **Total.** La regla es una condición sobre fechas |
| Costo del error | **Alto y asimétrico.** Duplicar erosiona la confianza; no enviar deja un ticket sin atender |
| Latencia | Ninguna. Hora fija |
| Determinismo | **Exigido.** «No puede duplicar» es una garantía, no una preferencia |
| Mantenimiento | Mínimo |

### La decisión: automatización tradicional, y la IA sería la peor opción

**No es que la IA sea innecesaria aquí. Es que es activamente peor.** El
requerimiento pide tres cosas y un modelo de lenguaje empeora las tres:

**1 · «El texto del mensaje es siempre el mismo».** Es una plantilla con dos
huecos. Un modelo generaría una variante distinta cada vez — exactamente lo
contrario de lo pedido, y encima habría que revisar que no dijera algo raro.

**2 · «No puede duplicar si se ejecuta dos veces».** Es idempotencia, y se
resuelve con una restricción de unicidad sobre `(ticket, tipo, fecha)`. Un
modelo no aporta nada y **añade una fuente de no determinismo** a un proceso
cuyo requisito central es ser determinista.

**3 · «Tres días hábiles».** Es aritmética de calendario con festivos. Una
consulta SQL o veinte líneas de código la resuelven exactamente. Un modelo la
resolvería **aproximadamente**, que en un plazo es simplemente mal.

Un modelo añadiría costo por llamada, latencia, una dependencia de red en un
proceso que debe correr sin supervisión a las 8:00, y **variabilidad donde se
pidió exactitud**.

### Diseño

```
cron 8:00 ─▶ SELECT tickets sin cambio ≥ 3 dias habiles
                    │
                    ├── ¿ya se envio hoy?   UNIQUE(ticket, tipo, fecha)
                    │      sí → omitir
                    ▼
              plantilla + {codigo, responsable}
                    ▼
              envio ── reintento con retroceso ── registrar el envio
```

La unicidad va **en la base y no en el código**: si el proceso corre dos veces
en paralelo —dos contenedores, un reintento del planificador— dos
comprobaciones en memoria pueden pasar las dos. La restricción de la base es
la única garantía real.

### Riesgo

**El proceso falla en silencio.** Un lote que no corre no genera error visible:
simplemente no llega ningún recordatorio, y nadie nota la ausencia de algo. Se
mitiga con una señal de vida y una alerta cuando no se recibe, no revisando
los registros.

### Bajo qué condición cambiaría

1. **El texto deja de ser fijo** y hay que redactar según el contexto del
   ticket. Ahí entra un modelo — pero con revisión, porque el mensaje sale a
   nombre de la compañía.
2. **La regla de escalamiento se vuelve dependiente del contenido**: «escala
   si el ticket parece urgente». Eso sí es clasificación, y es R-01 otra vez.
3. **Hay que decidir a quién escalar** por algo que no está en los datos. Un
   modelo podría proponerlo, con confirmación humana.

**Nada de eso está en el requerimiento actual.** Añadir IA hoy sería resolver
un problema que nadie tiene, pagando con determinismo.

---

## Lo que los tres tienen en común

**El criterio que decide no es el volumen ni la dificultad: es el costo del
error y si el problema tiene forma fija.**

```
R-01   error barato, forma fija, mucho volumen   → aprender de los datos, IA en la excepción
R-02   error caro, forma abierta, poco volumen   → IA, con abstención y cita obligatorias
R-03   error caro, forma fija, determinismo      → automatización. La IA solo estorba
```

R-02 y R-03 tienen el mismo costo del error, y decisiones opuestas. La
diferencia es que **R-03 tiene forma fija**: se puede escribir la regla
completa. Cuando se puede escribir la regla, escribirla siempre gana — es
exacta, gratis, determinista y se explica sola.

La IA sirve cuando **no se puede enumerar la entrada**. R-02 cumple eso; R-03
no; R-01 lo cumple solo en la cola de casos raros, y por eso ahí es una
excepción y no el motor.

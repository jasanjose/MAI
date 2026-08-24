# Calibración del umbral de abstención

> Reproducible con `python scripts/calibrar_umbral.py <carpeta_de_politicas>`.
> No corre en integración continua: necesita el corpus, que no se versiona.
> Esta página es su salida, con la lectura de los datos.

**Criterio, fijado en [`metricas.md`](metricas.md) §4 antes de tener datos:**
el umbral es *el valor más bajo que aún abstiene en el 100 % de los casos sin
respaldo*. La abstención es condición dura; la tasa de escalamiento (≤ 25 %)
es objetivo.

**Corpus:** 5 documentos · 67 fragmentos.
**Conjunto de referencia:** 21 consultas con respuesta verificada en sección ·
6 casos sin respaldo documental.

---

## 1. El techo: la recuperación no es el problema

```
recall@5 = 21/21 (100 %)
```

Para **las 21 consultas con respuesta, el fragmento correcto está entre los 5
recuperados.** La recuperación funciona. Todo lo que sigue es sobre dónde
poner la frontera, no sobre si se encuentra la evidencia.

## 2. Los puntajes, ordenados

| Sin respaldo — debe abstenerse | mejor puntaje |
|---|---:|
| `AB-002` ¿viáticos si viajo a Ciudad de México? | **0.411** |
| `AB-005` ¿cuándo pagan la prima de servicios? | 0.339 |
| `GS-003` ¿puedo trabajar desde casa tres días? | 0.237 |
| `AB-001` ¿días de licencia de paternidad? | 0.209 |
| `AB-003` ¿celular personal para el correo? | 0.185 |
| `AB-004` ¿auxilio educativo para posgrado? | 0.000 |

| Con respuesta — las cinco más bajas | mejor puntaje |
|---|---:|
| `CO-013` ¿longitud mínima de la contraseña? | 0.207 |
| `CO-007` ¿días para legalizar viáticos? | 0.209 |
| `CO-011` ¿en cuánto reportar el hurto del equipo? | 0.235 |
| `CO-009` ¿máximo diario de alimentación en capital? | 0.250 |
| `CO-003` ¿puedo compensar todas las vacaciones? | 0.257 |

**Los rangos se solapan por completo.** `AB-002`, que no tiene respuesta,
puntúa más alto que 18 de las 21 que sí la tienen.

## 3. Barrido

| umbral | responde bien | abstiene mal | abstiene bien | ≤25 % | 100 % |
|---:|---:|---:|---:|:--:|:--:|
| 0.18 | 21/21 | 0/21 | 1/6 | sí | **no** |
| **0.20** | **21/21** | **0/21** | **2/6** | **sí** | **no** |
| 0.22 | 19/21 | 2/21 | 3/6 | sí | no |
| 0.24 | 18/21 | 3/21 | 4/6 | sí | no |
| 0.26 | 15/21 | 6/21 | 4/6 | no | no |
| 0.34 | 8/21 | 13/21 | 5/6 | no | no |
| 0.40 | 3/21 | 18/21 | 5/6 | no | no |

**Ningún umbral cumple el 100 %.** Ni siquiera 0.40, que ya destruye la
utilidad del sistema —responde 3 de 21— sigue dejando pasar `AB-002`.

## 4. Por qué, y por qué no se arregla ajustando

`AB-002` puntúa 0.411 por **un solo término compartido**: `reconocen`, contra
`POL-ADM-04 §5.3` («Los gastos sin soporte válido no se reconocen»). Es un
fragmento muy corto, así que la normalización deja que ese término lo domine.

Ese diagnóstico apunta a BM25, que penaliza la longitud en vez de
normalizarla a ciegas. **Se midió, y no cambia la conclusión:**

| | recall@5 | peor con respuesta | mejor sin respaldo | margen |
|---|---:|---:|---:|---:|
| TF-IDF | 21/21 | 0.207 | 0.411 | **−0.204** |
| BM25 | 21/21 | 1.840 | 5.225 | **−3.385** |

`AB-002` gana en las dos porque **de verdad es léxicamente parecida** a la
política de viáticos: pregunta por viáticos, usa sus palabras y espera un
monto. Lo que la hace inválida es semántico —la política solo fija montos
nacionales y México no es uno— y ningún esquema de pesos de términos ve eso.

**Conclusión: el umbral de similitud, solo, no puede cumplir la abstención
del 100 %.** No es un problema de calibración: es el límite de la
recuperación léxica.

## 5. Qué se decide entonces

**Umbral = 0.20**, y con una función distinta de la que se le atribuye a un
umbral. No es el mecanismo de abstención: es **el primer filtro de dos**.

| | Qué le toca | Qué atrapa |
|---|---|---|
| **Puerta 1 · umbral 0.20** | descartar lo que no se parece a nada | `AB-003`, `AB-004` — 2 de 6 |
| **Puerta 2 · verificación de cita** | descartar lo que se parece pero no responde | `AB-001`, `AB-002`, `AB-005`, `GS-003` — los 4 restantes |

0.20 es el valor más alto que **no pierde ni una** de las 21 consultas
legítimas. Subirlo compra abstenciones caras: pasar a 0.22 gana un caso y
pierde dos respuestas buenas; llegar hasta 0.24 gana dos y pierde tres. Con
la puerta 2 haciendo el trabajo real, ese intercambio no vale la pena.

**Esto convierte la puerta 2 en portante, no en refuerzo.** Los cuatro casos
que quedan dependen de que el modelo, al recibir fragmentos que no contienen
la respuesta, diga `NO_TENGO_EVIDENCIA` en vez de improvisar — y de que la
verificación de cita descarte la respuesta si no lo hace. Por eso
[ADR-004](adr/ADR-004-desacoplamiento-proveedor-llm.md) pone la fidelidad
primero en `RUTA_RAG`: lo que se rompe en abstención es la complacencia del
modelo.

## 6. Lo que esto NO demuestra

**La abstención del 100 % no está verificada de extremo a extremo.** Está
verificada la puerta 1 con datos reales, y la puerta 2 con pruebas contra un
proveedor simulado —responde sin citar, cita algo que no recibió, se cae—.
Lo que falta es medir los cuatro casos restantes contra un modelo real.

Mientras eso no se haga, la afirmación honesta es: *el sistema abstiene
correctamente en 2 de 6 casos por recuperación, y los otros 4 dependen de un
comportamiento del modelo que está diseñado y probado en simulación, pero no
medido en producción.*

## 7. Bajo qué condición se revisaría

1. **Se conecta un proveedor real.** Hay que rehacer la medición completa,
   incluida la puerta 2, y esta página se reescribe con esos datos.
2. **Se cambia a un vectorizador de embeddings.** La sinonimia cambia todos
   los puntajes; el umbral no es transferible entre representaciones y hay
   que recalibrar desde cero.
3. **Crece el corpus.** Más fragmentos suben la competencia por el primer
   puesto y bajan los puntajes máximos.
4. **Aparece un caso sin respaldo que supere 0.411.** El conjunto de
   referencia tiene 6; seis casos no son una muestra, son un indicio.

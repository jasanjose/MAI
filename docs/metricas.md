# Métricas objetivo — definidas antes de implementar

**Proyecto:** MAI · Mesa de Ayuda Inteligente
**Fecha:** 21 de agosto de 2026
**Estado:** definido **antes** de escribir la primera línea de `src/`.

Este documento fija contra qué se mide la solución. Se escribe primero por
una razón concreta: un objetivo definido después de ver el resultado no es
un objetivo, es una descripción. El historial de Git es la evidencia de que
el orden fue este.

Lo que aquí se fija es exigible: la suite de evaluación de la etapa 5 lee
estos umbrales y **falla** cuando el resultado queda por debajo. No advierte.

---

## 1. El catálogo: 12 categorías

R-01 dice que las solicitudes se clasifican en 12 categorías estables desde
hace tres años. El histórico trae **58 variantes de escritura** de la
columna `categoria`. Al normalizar mayúsculas, tildes y espacios quedan 22;
al unir sinónimos evidentes (`aplicaciones`→Software, `equipos`→Hardware,
`conectividad`→Red, `reportes`→Informes, `ordenes de compra`→Compras,
`acceso`/`gestion de accesos`→Accesos) quedan **exactamente 12**.

Que el número coincida con el catálogo declarado confirma que el desorden
es de escritura, no de catálogo. Las 12 son el catálogo cerrado contra el
que se valida toda salida del modelo.

| Categoría | Registros | Banda |
|---|---:|---|
| Software | 303 | alto |
| Accesos | 298 | alto |
| Hardware | 230 | alto |
| Red | 172 | alto |
| Incidentes | 141 | medio |
| Nómina | 138 | medio |
| Compras | 126 | medio |
| Informes | 121 | medio |
| Vacaciones | 113 | medio |
| Otros | 106 | medio |
| Viáticos | 102 | medio |
| Capacitación | 82 | bajo |

Aparte quedan 68 registros con `categoria` vacía o `Sin clasificar`. **No
son una decimotercera categoría:** son ausencia de etiqueta. Se excluyen
del cálculo de precisión y se cuentan aparte como cobertura.

---

## 2. Precisión objetivo por categoría

| Banda | Categorías | Precisión mínima |
|---|---|---:|
| Alto (≥150 registros) | Software · Accesos · Hardware · Red | **0,80** |
| Medio (100–149) | Incidentes · Nómina · Compras · Informes · Vacaciones · Viáticos | **0,70** |
| Bajo (<100) | Capacitación | **0,60** |
| Cajón de sastre | Otros | **0,50**, declarado |

**Global: macro-F1 ≥ 0,75.**

Se usa macro-F1 y no exactitud porque el reparto va de 82 a 303 registros:
la exactitud premiaría acertar las cuatro grandes e ignorar Capacitación.
Macro-F1 pesa igual a las 12, que es lo que el negocio necesita.

`Otros` va con umbral propio y declarado porque es un cajón de sastre por
definición: no tiene frontera semántica, y exigirle lo mismo que a Hardware
distorsionaría el macro-F1 hacia abajo por una razón que no es de calidad
del modelo.

**Por qué 0,80 y no 0,95.** R-01 dice que la clasificación errada se
corrige en menos de un minuto y no afecta al usuario final, solo al
indicador de asignación. Pedir 0,95 sería gastar esfuerzo y costo en un
error barato. El umbral se sube el día que el error deje de ser barato —
por ejemplo, si la categoría empieza a disparar un flujo automático.

---

## 3. Latencia

| Flujo | p95 | Por qué ese valor |
|---|---:|---|
| Clasificación de un ticket | **≤ 5 s** | Corre en lote cada hora (R-01). No hay usuario esperando |
| Consulta de política (RAG) | **≤ 4 s** | Sí hay usuario esperando la respuesta |

Se mide p95 y no promedio: el promedio esconde la cola, y la cola es lo que
el usuario percibe como «el sistema está lento».

La latencia se mide **extremo a extremo** desde que entra la petición hasta
que sale la respuesta, incluyendo recuperación de fragmentos y reintentos.
No se mide solo la llamada al proveedor: eso mediría al proveedor, no a la
solución.

---

## 4. Escalamiento y abstención

| Métrica | Umbral | Naturaleza |
|---|---:|---|
| Tasa máxima de escalamiento a persona | **≤ 25 %** | Objetivo de eficiencia |
| Abstención ante pregunta sin evidencia | **100 %** | Condición dura |
| Respuestas emitidas sin cita verificable | **0** | Condición dura |

**El 25 % sale del negocio, no de la técnica.** R-02 dice que la mesa gasta
cerca del 18 % de su tiempo respondiendo consultas de política. Escalando
una de cada cuatro, se sigue recuperando la mayor parte de ese tiempo. Si
el escalamiento supera el 25 %, la solución deja de justificar su costo y
la decisión correcta es revisarla, no tolerarla.

**Las dos condiciones duras no admiten umbral parcial.** Una abstención del
95 % significa que uno de cada veinte usuarios recibe una respuesta
inventada sobre montos o plazos, sin forma de distinguirla de una correcta.
R-02 dice que eso genera reclamación formal ante Talento Humano. No es una
métrica que se optimiza: es una que se cumple o invalida el componente.

### Umbral de similitud — pendiente de calibración

El valor numérico que separa «tengo evidencia» de «no tengo evidencia» **no
se fija en este documento**. Se calibra contra el conjunto de referencia
(commit siguiente) buscando el valor más bajo que aún abstiene en el 100 %
de los casos sin respaldo documental.

Se deja pendiente a propósito: fijarlo ahora, sin datos, sería inventarlo.
Queda registrado aquí para que el historial muestre que el criterio de
calibración se definió antes que el número.

---

## 5. Costo

Toda llamada a un proveedor externo registra `latencia_ms`,
`tokens_entrada`, `tokens_salida`, `costo_estimado`, `proveedor`, `modelo` y
`resultado` (`exito` / `degradado` / `error`).

La estimación mensual con supuestos declarados y las cifras medidas contra
proveedores reales van en [`costos.md`](costos.md); el presupuesto máximo y
qué hace el sistema al superarlo, en [`arquitectura.md`](arquitectura.md) §7.
Aquí se fija la obligación de medir; allá el número.

**No se declara un objetivo de costo en este momento** porque no hay
medición todavía, y un objetivo de costo inventado no sirve para decidir
nada. Lo que sí se fija ahora es que ninguna llamada sale a producción sin
reportar su costo.

---

## 6. Umbrales que rompen la integración continua

La suite de evaluación falla el build cuando:

| Condición | Efecto |
|---|---|
| macro-F1 < 0,70 | ❌ falla |
| Cualquier caso sin evidencia respondido en vez de abstenido | ❌ falla |
| Cualquier respuesta emitida sin cita verificable | ❌ falla |
| p95 de clasificación > 5 s | ⚠️ advierte |
| p95 de consulta RAG > 4 s | ⚠️ advierte |

El corte de macro-F1 que rompe el build (0,70) es más bajo que el objetivo
(0,75) a propósito: el objetivo es hacia dónde se trabaja, el corte es
dónde se declara que la solución dejó de ser aceptable. Igualarlos haría
que el build fallara ante cualquier fluctuación normal.

La latencia advierte y no rompe porque depende de un proveedor externo cuya
disponibilidad no controlo. Un build rojo por lentitud ajena entrena al
equipo a ignorar los builds rojos.

---

## 7. Contra qué se mide

`docs/conjunto_referencia.csv` — mínimo 50 casos etiquetados a mano, que
incluyen obligatoriamente:

- Casos de clasificación de las 12 categorías
- Casos de consulta con respuesta explícita en los PDF
- **Casos de abstención**: preguntas cuyo tema no existe en el corpus
- Casos límite: texto ambiguo, texto vacío, texto en el que dos categorías
  compiten

El conjunto se etiqueta a mano antes de implementar. Un conjunto etiquetado
por el mismo sistema que se evalúa no mide nada.

---

## 8. Lo que este documento no fija

Declarado en vez de omitido:

- **Exhaustividad (recall) por categoría.** Se prioriza precisión porque el
  costo de asignar mal es visible e inmediato, y el de no asignar es que el
  ticket queda en `Sin clasificar`, que es un estado válido y revisable.
- **Objetivo de costo mensual.** Sin medición previa sería un número
  inventado. La medición llegó después y está en [`costos.md`](costos.md); el
  objetivo se fija sobre ella, no sobre una estimación.
- **Umbral de similitud.** Pendiente de calibración, §4.
- **Métricas de la pantalla Angular.** Fuera de alcance de este documento.

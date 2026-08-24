# ADR-003 · Estrategia de fragmentación del corpus de políticas

**Fecha:** 24 de agosto de 2026 · **Estado:** aceptada
**Decide:** en qué unidades se parte el corpus antes de indexarlo, y qué
tamaño tienen esas unidades.

---

## Contexto

El corpus son cinco políticas internas en PDF. Medido sobre los documentos
reales:

```
5 documentos · 37 secciones numeradas · 43 subsecciones · 2.037 palabras
```

Dos hechos condicionan la decisión, y los dos son propiedades de **estos**
documentos, no supuestos generales:

**1 · Los documentos ya vienen partidos.** Cada uno tiene secciones numeradas
—`3. Solicitud y aprobación`— y varias tienen subsecciones —`3.1.`, `3.2.`—.
Cada una es una regla completa: un plazo, un monto, una condición.

**2 · El corpus entero cabe en una petición.** 2.037 palabras son unos 3.000
tokens. Cualquier modelo actual los acepta de una vez.

Y una restricción del producto que pesa más que las dos: **toda respuesta
debe citar documento y sección**, o no se emite (`CLAUDE.md` §8). La
fragmentación no solo alimenta la recuperación: determina si la cita existe y
si es verificable.

---

## Alternativas consideradas

| Opción | A favor | En contra |
|---|---|---|
| **Por sección numerada, al nivel más fino** | **La cita sale de la estructura del documento**: `POL-GTH-01 §3.1` es exacta y quien la lea puede abrir el PDF y comprobarla. Cada fragmento es una regla completa. Cero parámetros que ajustar | Depende de que el documento esté numerado. Una política mal estructurada produce fragmentos de mala calidad, y no hay señal automática de que eso ocurrió |
| Ventana fija de N caracteres | Funciona con cualquier documento, numerado o no. Es lo que hace todo el mundo | **Parte reglas a la mitad**: «la solicitud debe radicarse con \| anticipación mínima de quince días». Y obliga a inventar identificadores de fragmento que no significan nada para una persona: `POL-GTH-01#chunk-7` no se puede verificar |
| Ventana fija con solapamiento | Mitiga el corte a la mitad duplicando texto en los bordes | El mismo texto aparece en dos fragmentos, así que compite consigo mismo en la recuperación y una respuesta puede citar cualquiera de los dos. Añade un segundo parámetro que ajustar sin datos para hacerlo |
| Documento completo como fragmento | Cinco fragmentos, ninguna regla partida | La cita se degrada a «POL-GTH-01», sin sección: quien la reciba tiene que leer dos páginas para verificar una cifra. Y con 400 palabras por fragmento, la similitud de una consulta corta se diluye |
| Sin fragmentar: todo el corpus en el prompt | Cabe. Ningún problema de recuperación, y el modelo ve todo el contexto | **Elimina la única señal objetiva de que no hay evidencia.** Sin puntaje de recuperación, la abstención depende por completo de que el modelo lo reconozca. Y paga 3.000 tokens de entrada en cada consulta, unas 80 veces al día |

---

## Decisión

**Fragmentar por la unidad numerada más fina disponible.** Si una sección
tiene subsecciones, cada subsección es un fragmento; si no, lo es la sección
entera.

**Una subsección hereda el título de su sección padre** en el texto que se
indexa. `§3.1` vive bajo «Solicitud y aprobación» y esa palabra no aparece en
su cuerpo, pero es la que alguien escribiría al preguntar. Los títulos se
anteponen una sola vez: repetirlos inflaría su frecuencia y haría que una
sección pareciera más relevante solo por llamarse como la pregunta.

**No se fija un tamaño objetivo de fragmento.** El tamaño es el que tenga la
regla. Medido, el resultado son **67 fragmentos de unas 25 palabras**, pero
ese número es una consecuencia, no un parámetro.

**Las secciones sin cuerpo propio se descartan** —aquellas cuyo contenido
vive entero en sus subsecciones—. Son 13, y el descarte se cuenta en el
reporte de ingesta en vez de silenciarse.

---

## Verificación

**Cobertura de vocabulario: 717 de 717.** Todas las palabras de cinco o más
letras del cuerpo de los cinco documentos aparecen en algún fragmento. Los 13
descartes no pierden contenido: sus títulos sobreviven como título padre de
sus subsecciones.

**recall@5 = 21/21** sobre las consultas del conjunto de referencia que
tienen respuesta verificada en sección. La fragmentación no es el cuello de
botella de la recuperación.

---

## Consecuencias negativas aceptadas

- **Depende de la numeración del documento.** Una política sin numerar
  produce un solo fragmento gigante o ninguno, y **no hay señal automática de
  que eso pasó**: el reporte de ingesta diría «1 fragmento» y habría que
  mirarlo. Es el riesgo más real de esta decisión.
- **El extractor de PDF tiene que conservar los saltos de línea.** La
  fragmentación se apoya en que las secciones empiecen a inicio de línea. Un
  extractor que devuelva texto corrido rompe todo el componente en silencio.
- **Las tablas quedan como texto corrido.** La de montos de viáticos y la de
  tiempos de atención pierden su estructura. Alcanza porque las cifras y sus
  etiquetas quedan en la misma línea, pero una tabla de verdad compleja no
  sobreviviría.
- **Fragmentos muy cortos distorsionan la similitud.** Con normalización L2,
  un fragmento de diez palabras que comparte un término raro con la consulta
  obtiene un coseno alto. Está medido y es la causa del problema de
  abstención documentado en [`calibracion_umbral.md`](../calibracion_umbral.md).
- **Una regla repartida entre dos secciones se cita a medias.** El caso
  `CO-011` del conjunto de referencia necesita `§5.1` y `§5.2` para responder
  completo. Se recuperan las dos entre las cinco, pero nada garantiza que el
  modelo cite ambas.

---

## Bajo qué condición se revisaría

1. **Entra un documento sin numeración.** Habría que detectarlo en la ingesta
   —un solo fragmento por documento es la señal— y decidir una estrategia
   alterna solo para él, en vez de cambiarla para todos.
2. **El corpus crece un orden de magnitud.** Con miles de fragmentos, los muy
   cortos compiten peor y la distorsión de similitud cambia de forma.
3. **Aparecen tablas que hay que consultar por celda.** «¿Cuánto es el
   hospedaje en municipio no capital?» hoy se responde porque la fila cabe en
   una línea. Con una tabla de veinte columnas dejaría de funcionar, y la
   respuesta sería extraerlas como estructura y no como texto.
4. **Se mide que el modelo cita solo una de dos secciones necesarias** con
   frecuencia. Entonces convendría agrupar las subsecciones de una misma
   sección en un fragmento y aceptar fragmentos más largos.

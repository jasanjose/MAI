# ADR-001 · Vectorización, índice y métrica de similitud

**Fecha:** 24 de agosto de 2026 · **Estado:** aceptada
**Decide:** cómo se convierte texto en vectores, dónde se guardan y cómo se
comparan.

---

## Contexto

Tras fragmentar ([ADR-003](ADR-003-fragmentacion.md)) el corpus son **67
fragmentos de unas 25 palabras**. Sobre esa escala hay que decidir tres cosas
que suelen tomarse juntas y son independientes: **con qué se representa el
texto**, **dónde se guarda** y **cómo se compara**.

Dos restricciones acotan el espacio:

**1 · Las pruebas corren sin red y sin credenciales.** Es la condición que
hace que la suite signifique algo en integración continua. Cualquier
representación que exija descargar pesos o llamar a un servicio la rompe.

**2 · Quien pregunta usa el vocabulario del documento.** Es un corpus
normativo: la gente escribe «viáticos», «reapertura», «anticipo». No es un
supuesto cómodo — es una propiedad del dominio que hace que la recuperación
léxica sea más competitiva de lo que sería sobre texto conversacional.

---

## A · Con qué se representa el texto

| Opción | A favor | En contra |
|---|---|---|
| **TF-IDF en Python puro, tras un puerto** | Determinista, instantáneo, cero dependencias. **Explicable término a término**: se puede señalar qué palabra hizo que un fragmento saliera primero. Corre en CI sin nada | **No reconoce sinonimia.** Está medido: «¿qué pasa si pierdo el computador?» no recupera su respuesta, que dice «Pérdida, hurto o daño» y nunca nombra el aparato |
| `sentence-transformers` local | Reconoce sinonimia sin credenciales | Descargar ~90 MB de pesos rompe «las pruebas no dependen de red», y es una dependencia grande para 67 fragmentos. En CI habría que cachear el modelo o aceptar minutos de arranque |
| Embeddings del proveedor por API | La mejor calidad, y ya hay adaptador para hablar con esos proveedores | Exige credencial en cada ejecución de la suite. Es exactamente lo que el adaptador falso existe para evitar |
| BM25 | Corrige la distorsión de los fragmentos cortos, que es un problema real aquí | **Se midió y no cambia la conclusión.** Ver abajo |

**Decisión: puerto `Vectorizador` con dos implementaciones.** `tfidf` en
Python puro por defecto y en CI; `remoto` contra el endpoint de embeddings
del proveedor, para producción. La decisión no es «TF-IDF»: es **que se pueda
cambiar sin tocar la recuperación**, y que el que no necesita red sea el
predeterminado.

**El puerto tiene dos métodos y no uno.** Un vectorizador que aprende del
corpus —TF-IDF necesita saber en cuántos documentos aparece cada término— lo
hace en `indexar`, y `consultar` usa esa representación aprendida. Con un
método genérico, quien lo implemente tendría que adivinar cuándo aprender, y
vectorizar la consulta con otro vocabulario produce similitudes que no
significan nada.

### Por qué se descartó BM25, con la medición

El diagnóstico apuntaba a BM25: los fragmentos cortos ganan de más porque la
normalización L2 deja que un término raro los domine. BM25 penaliza la
longitud en vez de normalizarla a ciegas. Se implementó y se midió sobre el
conjunto de referencia:

| | recall@5 | peor con respuesta | mejor sin respaldo | margen |
|---|---:|---:|---:|---:|
| TF-IDF | 21/21 | 0.207 | 0.411 | **−0.204** |
| BM25 | 21/21 | 1.840 | 5.225 | **−3.385** |

Los dos con margen negativo: una pregunta que el corpus **no cubre** puntúa
más alto que la peor pregunta legítima. BM25 no lo arregla porque el caso que
falla —«¿cuánto me reconocen de viáticos si viajo a Ciudad de México?»— **de
verdad es léxicamente parecido** a la política de viáticos. Lo que lo hace
inválido es semántico, y ningún esquema de pesos de términos ve eso.

Se descarta con medición, no por opinión. Y la conclusión general es más
importante que la elección: **ninguna representación léxica resuelve este
caso**, lo que convierte la verificación de cita en un control portante y no
en un refuerzo.

---

## B · Dónde se guardan los vectores

| Opción | A favor | En contra |
|---|---|---|
| **Lista en memoria** | 67 productos punto son microsegundos. Cero dependencias, cero estado que administrar | Se reconstruye en cada arranque —irrelevante: la ingesta completa tarda menos de un segundo— y no escala a millones |
| Chroma | Persistencia y búsqueda aproximada listas para usar | Una dependencia grande que **no acelera nada medible** a esta escala, y que habría que instalar, versionar, explicar y mantener |
| FAISS | El índice aproximado más rápido | Lo mismo, y además compilado: complica la instalación en CI para resolver un problema que no se tiene |

**Decisión: lista en memoria, búsqueda exacta.** A 67 elementos, un índice
aproximado es una aproximación de algo que ya es instantáneo — cambia
exactitud por una velocidad que no hace falta.

El índice implementa `RecuperadorDeFragmentos`, así que el día que haga falta
una base vectorial entra como otro adaptador y el servicio de consulta no se
entera.

---

## C · Cómo se comparan

| Opción | A favor | En contra |
|---|---|---|
| **Coseno** | Mide **dirección y no magnitud**: qué proporción del vector va en la misma dirección. Un fragmento largo no gana por largo | Ignora la magnitud, que a veces informa |
| Distancia euclidiana | Intuitiva | **Un fragmento largo tiene más términos y por tanto un vector más largo**, así que queda lejos de todo aunque hable exactamente del tema. Sobre texto de longitud variable mide sobre todo el tamaño |
| Producto punto sin normalizar | El más barato | Equivale a premiar los fragmentos largos: es la distancia euclidiana con el problema al revés |

**Decisión: coseno.** Y con una consecuencia práctica: como los vectores se
normalizan a longitud 1 al construirlos, **el coseno es el producto punto** y
la comparación cuesta una multiplicación por dimensión. La normalización no
es un paso extra: es lo que permite que el paso caro desaparezca.

**Detalle que importa:** un vector nulo —una consulta sin ningún término
conocido— da coseno cero contra todo. Eso no es un caso degenerado que haya
que tratar aparte: **es exactamente la señal de que no hay evidencia**, y el
servicio de consulta la usa como tal.

---

## Consecuencias negativas aceptadas

- **No hay sinonimia.** Medido: «pierdo» contra «pérdida» no coincide, y un
  stemmer de sufijos tampoco lo salvaría porque difieren en la diptongación
  de la raíz. Hay consultas legítimas que no recuperan su respuesta.
- **El vocabulario se aprende del corpus.** Un término que no aparece en
  ningún fragmento se ignora en la consulta. Es correcto —no puede ayudar a
  elegir— pero significa que el sistema no distingue «palabra rara» de
  «palabra que no existe».
- **El índice se reconstruye en cada arranque.** Con 67 fragmentos es
  imperceptible; con cien mil habría que persistirlo.
- **Un índice y su vectorizador van juntos.** Consultar con otro produce
  vectores de vocabularios distintos. Está protegido con una comprobación de
  tamaño que falla en vez de devolver un número plausible.
- **El umbral no es transferible entre representaciones.** Si se cambia a
  embeddings, los puntajes cambian de escala y hay que recalibrar desde cero.

---

## Bajo qué condición se revisaría

1. **Se conecta un proveedor real y se puede medir el vectorizador remoto.**
   Es la comparación pendiente y la que decide si TF-IDF era suficiente. El
   puerto existe para que esa comparación no cueste una reescritura.
2. **El corpus supera unos pocos miles de fragmentos.** Ahí la búsqueda
   exacta deja de ser instantánea y la persistencia del índice empieza a
   importar.
3. **Se mide que las consultas usan vocabulario distinto del documento.** Si
   la gente pregunta «¿cuándo me dan días libres?» en vez de «vacaciones», la
   ventaja de lo léxico desaparece y los embeddings pasan a ser obligatorios.
4. **Aparece necesidad de filtrar por metadatos** —por documento, por
   vigencia— junto con la similitud. Una base vectorial resuelve eso de
   fábrica; una lista obliga a escribirlo.

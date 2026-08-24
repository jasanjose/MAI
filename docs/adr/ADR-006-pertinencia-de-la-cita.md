# ADR-006 · La cita verificable no garantiza la respuesta correcta

**Fecha:** 24 de agosto de 2026 · **Estado:** aceptada
**Decide:** qué se hace con el hueco que dejan las dos puertas de abstención,
descubierto al medir contra proveedores reales.

---

## Contexto

El sistema no emite una respuesta de política sin cita, y lo hace con dos
controles independientes: un **umbral de similitud** que descarta lo que no se
parece a nada del corpus, y una **verificación de cita** que descarta lo que se
parece pero cuya respuesta no cita, o cita algo que no recibió.

Al medir la abstención de extremo a extremo contra tres modelos reales
([`costos.md`](../costos.md)), apareció un caso que **ninguna de las dos
puertas ve**. Es una pregunta por el viático de una ciudad extranjera; el
corpus solo tiene montos nacionales.

- La primera puerta no lo descarta porque **léxicamente sí se parece**: habla
  de viáticos y de una ciudad. [`calibracion_umbral.md`](../calibracion_umbral.md)
  ya lo había medido antes de que existiera este documento — puntúa más alto
  que 18 de las 21 consultas legítimas, y ningún umbral lo separa sin perder
  consultas buenas.
- La segunda tampoco, y **esto no estaba previsto**: el modelo cita de verdad
  un fragmento que se le entregó. La cita es auténtica y verificable contra lo
  recuperado. Lo que no es cierto es que ese fragmento responda la pregunta.

El enunciado del problema, en una frase: **verificar que una cita existe no
verifica que sea pertinente.** El control comprueba procedencia, no
suficiencia.

Dos modelos de tres fallan este caso; uno lo resuelve y abstiene en el 100 %.

---

## Alternativas consideradas

| Opción | A favor | En contra |
|---|---|---|
| **Configurar el modelo que sí cumple** | Cero código, cero dependencias. Ya medido al 100 %. La suite lo vigila en cada ejecución y **rompe el build** si deja de cumplirse | Depende de un proveedor concreto. Si ese modelo desaparece o se degrada, el sistema vuelve al 83 % |
| **Vectorizador remoto (embeddings)** | El puerto `Vectorizador` ya existe para esto. Resolvería la sinonimia que el README declara medida | **No ataca este defecto.** La recuperación ya va al 100 %: el fragmento correcto se recupera siempre. El fallo ocurre después, al generar |
| **Reranker sobre los fragmentos recuperados** | Es el componente que la industria usa para ordenar por pertinencia | Un reranker mide **relevancia**, no **implicación**. El fragmento de montos nacionales es tópicamente relevantísimo a una pregunta de viáticos; lo puntuaría alto igual que la primera puerta |
| **Tercera puerta: verificar que el fragmento citado contiene el dato pedido** | Ataca la causa, no el síntoma | Exige extraer de la pregunta *qué* dato se busca y comprobarlo contra el fragmento. Es un componente nuevo, con su propio modo de fallo, y sin conjunto de referencia que lo evalúe |
| **Subir el umbral de similitud** | Una línea | Medido en `calibracion_umbral.md`: ningún valor separa este caso sin perder consultas legítimas. Cambia un falso negativo por varios falsos positivos |

---

## Decisión

**Se configura el modelo que cumple, y el hueco se declara.**

La suite de evaluación es la que sostiene la decisión: mide la abstención en
cada ejecución contra los 6 casos sin respaldo y **termina en 1** si no llega
al 100 %. No es un informe: es una barrera. Un cambio de modelo que empeore la
abstención rompe el build antes de llegar a producción.

Se elige esto y no la tercera puerta por una razón de orden: **construir un
control cuya eficacia no se puede medir es peor que declarar el hueco.** No
hay hoy un conjunto de referencia de pertinencia —los 6 casos de abstención no
bastan para calibrar un verificador de suficiencia— y un control mal calibrado
que rechace respuestas correctas es más caro que el caso que deja pasar.

---

## Consecuencias negativas aceptadas

- **El sistema depende de un modelo concreto para cumplir una condición
  dura.** Es exactamente el acoplamiento que ADR-004 existe para evitar, y aquí
  se acepta a sabiendas: la alternativa es un componente sin medir. La cadena
  de reserva sigue funcionando, pero un modelo de reserva **puede abstener
  menos que el primario**, y eso hoy no se detecta en caliente — solo en la
  siguiente ejecución de la suite.
- **Con otro corpus el número cambia.** El 100 % está medido sobre cinco
  políticas y seis preguntas sin respaldo. No es una propiedad del modelo: es
  una medición sobre este corpus.
- **Queda un modo de fallo conocido y abierto**: una pregunta cuyo tema existe
  en el corpus pero cuyo caso concreto no. Es el más peligroso de todos,
  porque la respuesta llega con una cita real y el usuario no tiene forma de
  distinguirla de una correcta.

---

## Bajo qué condición se revisaría

- **Si el modelo que cumple deja de estar disponible o baja del 100 %.** La
  suite lo detecta sola. La primera carta a jugar entonces es el reranker,
  aceptando que mide relevancia y no implicación, y midiéndolo contra estos
  mismos 6 casos antes de confiar en él.
- **Si el corpus crece.** Más documentos significa más fragmentos tópicamente
  cercanos y sin el dato pedido: el hueco se ensancha con el tamaño del corpus,
  no se estrecha.
- **Si aparece un segundo caso de este tipo** en producción o en el conjunto de
  referencia. Uno es un caso; dos es un patrón, y entonces la tercera puerta
  tiene con qué calibrarse — que es justo lo que hoy le falta.

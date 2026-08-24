# Declaración de uso de asistentes de IA

> Se declara porque declararlo es parte del método, no un requisito que
> cumplir. Lo que sigue es específico a propósito: una declaración vaga
> —«usé IA para acelerar»— no dice nada verificable sobre cómo se trabajó.

---

## 1 · ¿Qué herramientas usaste y para qué?

**Claude Code (Opus 5)**, en sesión interactiva sobre este repositorio,
durante los tres días. Se usó para todo el ciclo: proponer diseños con
alternativas, escribir código y pruebas, ejecutar y medir, y redactar
documentación.

**No se usó** ningún asistente para decidir la arquitectura sin contraste:
cada decisión estructural —cómo abstraer el proveedor de lenguaje, dónde
guardar las solicitudes, cómo fragmentar los PDF, si traer una base
vectorial— se presentó como tabla de alternativas con su costo, y la elección
fue mía. Esas tablas están en `docs/decisiones.md` y en los ADR, y son
auditables: cada una nombra lo que se descartó.

Se usó además el propio repositorio como herramienta de verificación: `ruff`,
`bandit`, la suite de pruebas y la ejecución real de la aplicación.

---

## 2 · ¿Qué generaste y conservaste tal cual?

- **La estructura del paquete** y la configuración de herramientas.
- **El adaptador `compatible`** para proveedores que hablan Chat Completions.
  Un archivo para cinco proveedores; se conservó sin cambios porque la forma
  del protocolo no admite variantes interesantes.
- **El grueso de las 519 pruebas.** Los nombres describen comportamiento y
  las docstrings explican por qué existe cada caso de borde; eso se revisó,
  no se aceptó a ciegas.
- **El flujo de integración continua**, que corrió en verde a la primera.

---

## 3 · ¿Qué generaste, tuviste que corregir y por qué?

Seis correcciones que valen la pena, porque muestran qué tipo de error
comete un asistente y dónde hay que mirar.

**1 · Comparación de texto sin normalizar.** Las reglas de clasificación
comparaban contra literales acentuados. Un ticket que decía «no puedo entrar
al sistema de **nomina**» —sin tilde, como escribe la mayoría— recibía
categoría «Otros». **Con 300 pruebas en verde.** Se encontró levantando la
aplicación, no ejecutando la suite: todas las pruebas usaban texto bien
acentuado. Corregido rojo→verde.

**2 · Una corrección que estrechó el contrato.** Al arreglar el defecto S3
del módulo heredado se sustituyó una comparación de igualdad —que acepta
cualquier tipo— por una normalización de texto, que exige texto. Un `estado`
no textual pasó de no contarse a lanzar `AttributeError` y tumbar el informe.
Se encontró atacando la función con tipos inesperados. Corregido rojo→verde.

**3 y 4 · Dos pruebas de concurrencia que no probaban nada.** El asistente
escribió pruebas afirmando que demostraban una condición de carrera. Se
verificaron sustituyendo la implementación por una deliberadamente rota: las
dos **siguieron pasando**. Bajo el GIL de CPython la ventana es demasiado
estrecha. En el segundo caso se aisló el efecto llamando al registro
directamente —64 hilos, 500 claves— y ahí sí apareció un duplicado, en una de
dos corridas. Las docstrings se reescribieron para decir lo que la prueba
realmente es: red de regresión, no demostración.

**5 · Una afirmación falsa en un comentario.** El `.mailmap` decía que «los
primeros commits» se firmaron con otra cuenta y que «de ahí en adelante» con
la correcta. Al medirlo, **los 19 eran de la cuenta antigua** y no existía
ninguno de la nueva. Se corrigió antes de commitear.

**6 · Un error de razonamiento sobre la herramienta.** Se afirmó que empujar
siete commits produciría siete ejecuciones de CI. Falso: se crea una por
*push*, sobre el commit de punta. Los tres commits rojos no dispararon nada y
la evidencia de CI fallida no se produjo. Se corrigió empujando una rama que
apunta al commit rojo, y desde entonces los commits se empujan de uno en uno.

**El patrón que dejan las seis:** el asistente escribe código que funciona en
el caso que imaginó, y afirma con seguridad cosas que no midió. Lo que las
encontró no fue leer el código: fue **ejecutar la aplicación de verdad** y
**romper la implementación a propósito para ver si la prueba lo notaba**.

---

## 4 · ¿Qué decidiste escribir a mano y por qué?

**Aquí la respuesta honesta incomoda, y la doy completa.**

El plan de trabajo reservaba cuatro fragmentos para escribir a mano —la
lógica de idempotencia, el umbral de abstención, la regla de deduplicación y
la causa raíz de los tres defectos heredados— por ser los más probables de
sustentar. **No se cumplió en los términos previstos.** El código de esos
cuatro lo escribió el asistente; sobre la idempotencia se ofreció
explícitamente el reparto —yo escribo la función crítica, el asistente la
plomería— y elegí que la escribiera él.

Lo que sí fue mío, y es distinto de escribir las líneas:

- **Las decisiones de diseño**, tomadas sobre alternativas con su costo
  declarado: puerto genérico frente a específico, un adaptador frente a cinco,
  memoria frente a SQLite, TF-IDF frente a embeddings, sin base vectorial.
- **El umbral de abstención en 0.20**, elegido con la tabla de calibración
  delante y entendiendo lo que la medición obligaba a aceptar: que ningún
  valor cumple la abstención del 100 % y que el umbral es el primero de dos
  filtros, no el mecanismo.
- **La frontera entre lo que va al repositorio y lo que no.** Detecté que los
  mensajes de commit citaban el enunciado y pedí corregirlo; la regla quedó
  escrita y se aplicó también a los ADR y al README.
- **El alcance.** Qué se construye, qué se documenta y qué se declara como no
  hecho.

**Lo que esto significa para la sustentación:** puedo explicar por qué cada
pieza es como es y qué se descartó, porque esas decisiones las tomé yo con
los costos delante. Sobre las líneas concretas de `reservar` y de las causas
raíz del legacy, mi comprensión viene de haberlas revisado y discutido, no de
haberlas tecleado. Prefiero decirlo aquí a que se note allá.

---

## 5 · ¿Cómo verificaste lo generado?

Cinco mecanismos, en orden de cuánto encontraron:

**1 · Ejecutar la aplicación de verdad.** Levantar el servidor y hacerle
peticiones encontró **tres defectos que 300 pruebas en verde no vieron**: el
de las tildes, y dos huecos de diagnóstico en la sonda de salud. Una suite
verde no dice que el código funcione con datos reales; dice que funciona con
los datos que se le ocurrieron a quien la escribió.

**2 · Romper la implementación a propósito.** Antes de creer que una prueba
protege algo, se sustituyó el código por una versión deliberadamente
defectuosa para ver si la prueba lo notaba. Así se descubrió que las dos
pruebas de concurrencia no tenían dientes, y que BM25 no resolvía el problema
de abstención que parecía resolver.

**3 · Medir contra los datos reales, no contra ejemplos.** Cada corrección
del módulo heredado se cuantificó sobre los 2.000 registros: S1 recupera 16
tickets, S3 lleva la tasa de reapertura de 8,25 % a 26,4 %. La fragmentación
se validó por cobertura de vocabulario: 717 de 717 palabras del cuerpo
original aparecen en algún fragmento.

**4 · Análisis estático como enfoque, no como sustituto.** `ruff` detectó
solo, en cuanto el módulo heredado entró al repositorio, el argumento mutable
por defecto —el defecto S2—. No detectó S1 ni S3, que son de lógica. Ese
contraste define bien qué revisa una herramienta y qué tiene que revisar una
persona.

**5 · Rojo antes que verde, sin excepción.** Cada defecto corregido tiene su
prueba fallando en un commit anterior al arreglo. Son cuatro pares en el
historial. Sin la prueba en rojo previa no hay evidencia de haber entendido
la causa; solo de que el síntoma dejó de verse.

---

## Trazabilidad

El registro completo del uso —qué se generó, qué se corrigió y por qué, y
qué se verificó, sesión por sesión— se llevó en vivo durante los tres días.
No se reconstruyó al final: reconstruirlo de memoria produce una declaración
vaga, y la especificidad de este documento viene de haberlo anotado mientras
ocurría.

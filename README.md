# MAI · Mesa de Ayuda Inteligente

Solución por etapas para la Prueba Técnica de Nivelación de perfiles IA de
LA FORTUNA S.A. Recibe solicitudes internas escritas en texto libre, las
sanea, las clasifica, las responde con base en las políticas vigentes y
escala a una persona lo que no puede resolver.

---

## Estado de la entrega

| Etapa | Estado | Dónde está |
|---|---|---|
| 1 · Fundamentos | ✅ **completa** | `src/mai/`, `sql/`, `tests/` |
| 2 · Autonomía e integración | ✅ **completa**, incluido el opcional | `src/mai/api/`, `src/mai/adaptadores/llm/`, `legacy/`, `frontend/` |
| 3 · Complejidad y calidad | ✅ **completa** | `src/mai/rag/`, `docs/informe_seguridad.md`, `docs/guia_equipo.md` |
| 4 · Arquitectura | ✅ **documentada** | `docs/arquitectura.md`, 5 ADR |
| 5 · Estrategia | ✅ **completa** | `docs/decision_requerimientos.md`, `docs/comparacion_enfoques.md`, `src/mai/evaluacion/` |

**Lo que quedó fuera está declarado en la sección «Límites», al final.** No
está escondido: reconocer un límite es información útil para quien mantiene
el sistema.

### Lo más importante que hay que saber antes de leer el código

**Las dos tareas están medidas contra proveedores reales.** Clasificación y
consulta de políticas corrieron sobre el conjunto de referencia con modelos de
verdad: exactitud, latencia, tokens y costo están en
[`costos.md`](docs/costos.md). **La solución completa cuesta menos de seis
dólares al mes** con el volumen que declara el negocio. Con la configuración
por defecto —`RUTA_*=falso`— toda consulta de política **se abstiene**, y eso es
correcto: el adaptador de pruebas no cita, y una respuesta sin cita verificable
no se emite.

Cinco cosas que este proyecto midió y que cambian cómo se lee el resto:

| Hallazgo | Dónde |
|---|---|
| **Ningún umbral de similitud cumple la abstención del 100 %.** No es un problema de calibración: es el límite de la recuperación léxica. Por eso la verificación de cita es un control portante y no un refuerzo | [`calibracion_umbral.md`](docs/calibracion_umbral.md) |
| **El 99 % de precisión del clasificador clásico era falso.** 2.000 filas con 50 asuntos distintos: partiendo por asunto queda por debajo de la línea base | [`comparacion_enfoques.md`](docs/comparacion_enfoques.md) |
| **El modelo más caro no acierta más.** Dos modelos de proveedores distintos aciertan lo mismo —28 de 29— y uno cuesta **3,9 veces** lo que el otro; el caro consume incluso menos tokens | [`costos.md`](docs/costos.md) |
| **La primera puerta de abstención también ahorra dinero.** Dos de cada veintisiete consultas se descartan por umbral **sin llegar al modelo**: un 7 % de llamadas que no se pagan, y la puerta se puso para no inventar, no para ahorrar | [`costos.md`](docs/costos.md) |
| **La integración continua estuvo 37 ejecuciones en rojo sin detectarse**, por un falso positivo del detector de secretos. Lo relevante no es el falso positivo: es que se había dejado de correr la verificación completa | [`integracion_continua.md`](docs/integracion_continua.md) |

---

## Verificación rápida

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest          # 519 pruebas, sin red ni credenciales
ruff check .
bandit -r src/
```

Sin nada más: sin base de datos, sin Docker, sin claves.

---

## Instalación

Requiere **Python 3.11 o superior**. Sin base de datos, sin Docker, sin
servicios externos para correr las pruebas.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

La única dependencia de ejecución es `httpx`. Está justificada en
[`docs/decisiones.md`](docs/decisiones.md), igual que las de desarrollo
(`pytest`, `ruff`, `bandit`) y —más importante— igual que **las que se
decidieron NO usar**.

## Ejecución

### Sanear el histórico

```bash
python -m mai.limpiar_historico ruta/al/tickets_historicos.csv --salida salida
```

Produce tres archivos en el directorio de salida y un reporte por consola:

| Archivo | Contenido |
|---|---|
| `tickets_limpios.csv` | Registros que superaron normalización y validación |
| `cuarentena.csv` | Los apartados, **con su motivo y su fila original completa** |
| `resumen.csv` | Totales por área y por prioridad |

Códigos de salida, para que el proceso sirva dentro de una tubería y no solo
a mano:

| Código | Significa |
|---:|---|
| `0` | Terminó. Incluye el caso de archivo vacío: cero registros es un resultado válido, no un error |
| `1` | No pudo leer la entrada (no existe, o no es texto UTF-8) |
| `2` | Más del 10 % de los registros quedó en cuarentena. Ahí el problema no son los datos: es la fuente |

El umbral se ajusta con `--umbral-cuarentena`.

### Pantalla de Angular

El opcional con puntaje de la etapa 2: una pantalla que consume la API y
muestra el listado con filtros por área, estado, categoría y prioridad.

```bash
MAI_ORIGENES_PERMITIDOS=http://localhost:4200 python -m mai.api   # terminal 1
cd frontend && npm install && npm start                            # terminal 2
```

**Sin `MAI_ORIGENES_PERMITIDOS` el navegador bloquea las llamadas.** La API no
autoriza ningún origen cruzado por defecto y **no acepta `*`**: un comodín
permitiría que cualquier página abierta en el navegador del usuario la
llamara. Detalles en [`frontend/README.md`](frontend/README.md).

La pantalla **marca las clasificaciones degradadas**, con su motivo. No es
decoración: una categoría puesta por la regla de reserva acierta menos que una
del modelo, y tratar las dos igual es el error más probable al integrarse.

### Levantar la API

```bash
python -m mai.api                       # 127.0.0.1:8000
uvicorn mai.api.main:app --port 8000    # equivalente
```

Sin variables de entorno funciona: las dos rutas de proveedor caen en `falso`,
determinista y sin red. Qué resuelve, para quién y qué **no** hace está en
[`docs/api.md`](docs/api.md); el contrato técnico se genera del código y se
publica en `/openapi.json`, con navegador en `/docs`.

### Pruebas

```bash
pytest          # 519 pruebas, sin red y sin credenciales
ruff check .
bandit -r src/
```

**Ninguna prueba necesita red, credenciales ni los materiales originales.**
Usan `tests/fixtures/tickets_muestra.csv`, un archivo curado a mano.

### Integración continua

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre esas mismas tres
órdenes en cada envío, sobre Python 3.11 —el mínimo declarado en
`pyproject.toml`—, y añade un segundo trabajo que audita el repositorio:
credenciales en los archivos versionados, credenciales **en el historial**
(con `fetch-depth: 0`, porque un secreto borrado después sigue estando ahí) y
rutas privadas que no deberían estar versionadas.

El disparador no filtra por rama a propósito. El trabajo que debe fallar
ocurre en ramas de etapa, no en `main`; un vigilante que solo escucha `main`
no registra nada de lo que pasa donde de verdad se trabaja.

### Reproducir con los materiales originales

Los materiales entregados por la empresa **no se versionan** (ver
«Seguridad»). Para reproducir, colóquelos en `INSUMOS/` conservando su
estructura:

```
INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/
├── datos/tickets_historicos.csv
├── datos/esquema.sql
├── politicas/*.pdf
├── legacy/legacy_module.py
└── servicio_mock/
```

Para el servicio simulado:

```bash
cd INSUMOS/Materiales_Prueba_Tecnica_IA/materiales/servicio_mock
pip install -r requirements.txt
uvicorn app:app --port 8080
```

> El puerto es configurable con `MAI_MOCK_URL`. Durante el desarrollo el 8080
> estaba ocupado por otro servicio de la máquina y se usó uno libre; nada del
> código está atado a un puerto.

---

## Qué hace

### Saneamiento del histórico

Sobre los 2.000 registros entregados:

```
2000 leídos = 1960 limpios + 40 en cuarentena
  40  duplicado_exacto
  68  categoria → Sin clasificar
  51  area → Sin área
```

- **Fechas** en los tres formatos del histórico (`2025-03-08`, `08/03/2025`,
  `08-Abr-2025`) con **mapa explícito de meses en español**.
- **Catálogos**: las 58 variantes de escritura de `categoria` se reducen a
  las 12 del catálogo de servicios; 14 de prioridad a 4; 11 de estado a 5;
  7 de canal a 4.
- **Validación con cuarentena**: nada se descarta en silencio. Cada registro
  apartado conserva su motivo y su fila original.
- **Deduplicación** tras normalizar (ver «Supuestos»).
- **Reporte de calidad** que cuadra por construcción: leídos = limpios +
  cuarentena, con una prueba que lo verifica.

### Consumo del servicio externo

[`src/mai/adaptadores/http/cliente_solicitudes.py`](src/mai/adaptadores/http/cliente_solicitudes.py)
— GET y POST con tiempo de espera explícito, reintento con retroceso
exponencial, respeto de `Retry-After` y soporte de `Idempotency-Key`.

El servicio falla a propósito: 12 % de 500 y 5 % de 429. Verificado contra
él: **40 de 40 llamadas exitosas**, 2 necesitaron reintento.

Ninguna excepción de la librería llega al usuario: se traducen a errores del
dominio con mensaje legible.

### Módulo de IA desacoplado

La lógica de negocio depende de `ProveedorLLM`
([`src/mai/dominio/puertos.py`](src/mai/dominio/puertos.py)), nunca de un
proveedor concreto. Cambiar de modelo es cambiar `RUTA_CLASIFICACION` o
`RUTA_RAG`; no hay una línea de dominio que tocar.

| Adaptador | Para qué |
|---|---|
| `falso` | Determinista, sin red. Es lo que hace que las 519 pruebas corran en integración continua sin credenciales |
| `compatible` | Un archivo para **cinco proveedores** — Groq, DashScope, OpenAI, OpenRouter y Ollama hablan todos Chat Completions |
| `enrutador` | Cadena con reserva. **Implementa el mismo puerto**, así que el dominio no distingue un proveedor de una cadena de cinco |

Al agotarse la cadena **no responde un adaptador falso**: entra el modo
degradado, que es distinto según la tarea. Clasificar cae a reglas por
palabras clave marcadas `confianza: "baja"`; responder una política se
abstiene. La razón está en
[ADR-004](docs/adr/ADR-004-desacoplamiento-proveedor-llm.md).

El texto del usuario viaja **por un canal distinto** al de la instrucción
—rol `user` frente a rol `system`—, delimitado y con orden explícita de
tratarlo como dato. La salida se valida contra el catálogo cerrado de 12
categorías antes de aceptarse.

### Corrección del módulo heredado

[`legacy/legacy_module.py`](legacy/legacy_module.py) — los tres defectos
reportados, cada uno con su prueba en rojo antes del arreglo.

| | Causa raíz | Efecto medido sobre los 2.000 registros |
|---|---|---|
| **S1** | El docstring define el periodo como cerrado; la condición usaba comparadores estrictos | El informe trimestral pasa de 311 a **327** tickets |
| **S2** | Argumento mutable por defecto: se evalúa una vez al definir la función y lo comparten todas las llamadas | Deja de inflar cifras **y** de mutar un resumen ya entregado |
| **S3** | Comparación exacta contra un literal, sobre un dato que llega escrito de tres formas | Tasa de reapertura de **8,25 % a 26,4 %** (+363 tickets) |

El cambio total al módulo son **tres líneas de lógica**: se corrigió lo que
estaba mal, no se reescribió.

### Consulta de políticas con citas y abstención

`POST /consultas` responde en lenguaje natural **citando documento y
sección**, o declara que no tiene evidencia. Los cinco PDF se fragmentan por
sección numerada, de modo que la cita —`POL-GTH-01 §3.1`— sale de la
estructura del documento y quien la lea puede comprobarla.

**Dos puertas, y ninguna sobra:**

| | Qué descarta |
|---|---|
| **Umbral de similitud** | Lo que no se parece a nada del corpus. Se abstiene **sin llamar al modelo** |
| **Verificación de cita** | Lo que se parece pero no responde: si el modelo no cita, o cita algo que no recibió, la respuesta se descarta |

La segunda no es un refuerzo: es **portante**. La calibración
([`docs/calibracion_umbral.md`](docs/calibracion_umbral.md)) demostró que
ningún umbral cumple la abstención del 100 % —una pregunta sobre viáticos a
Ciudad de México puntúa más alto que 18 de las 21 consultas legítimas— y que
BM25 tampoco lo resuelve.

Sin proveedor, este componente **se abstiene**; no cae a reglas, a diferencia
de la clasificación. Responder mal sobre un plazo cuesta una reclamación
formal; clasificar mal cuesta un minuto de un analista.

### Observabilidad

`GET /metricas` — latencias p50/p95/p99 por operación, tasa de degradación y
de abstención **con su desglose por motivo**, y tokens por proveedor,
separando los que el modelo gastó razonando —que van dentro de los de salida,
no aparte, y son lo único que distingue un modelo verboso de uno que razona de
más—. El
desglose es lo que hace accionable la tasa: un proveedor caído y un modelo
que devuelve basura degradan igual y exigen acciones opuestas.

Registro estructurado en JSON con `id_traza` propagado extremo a extremo, sin
datos personales ni contenido de tickets.

### Consultas SQL

[`sql/consultas.sql`](sql/consultas.sql) — agregación por área, join de tres
tablas y tickets reabiertos, **más los índices propuestos con su
justificación** (el esquema no trae ninguno a propósito y pide proponerlos).

Se declara también **qué no se indexa y por qué**: `categoria`, `prioridad`
y `canal` tienen 12, 4 y 4 valores distintos; indexar baja cardinalidad es
coste de escritura sin beneficio de lectura.

---

## Supuestos

Decisiones que se tomaron por criterio y que otro podría tomar distinto.

1. **Las 12 categorías salieron de los datos, no de una lista dada.** Las 58
   variantes colapsan en 12 al unir sinónimos, y R-01 declara 12. La
   coincidencia es la evidencia de que el catálogo es ese.
2. **`fecha_cierre` vacía es un ticket abierto, no un dato sucio.** Son 1.299
   registros. Tratarlos como error de calidad rompería el dato.
3. **«Sin clasificar» y la celda vacía son lo mismo**: ausencia de etiqueta.
   No se crea una decimotercera categoría.
4. **`reaperturas` vacío cuenta como cero.** No haber reabierto es un dato.
5. **Un ticket Reabierto, Escalado o En proceso cuenta como abierto**: es
   trabajo pendiente.
6. **La tasa de reapertura cuenta tickets, no reaperturas.** Un ticket con
   tres reaperturas es un ticket reabierto, no tres.
7. **`formulario` y `Formulario web` se unieron en un solo canal.** Es la
   interpretación razonable, pero —a diferencia de los sinónimos de
   categoría— no es un hecho verificable. Si son dos canales distintos, se
   separan en una línea de `catalogos.py`.
8. **Deduplicación: se normaliza primero y se deduplica después.** Los 12
   identificadores repetidos «con contenido distinto» resultaron ser el mismo
   ticket capturado dos veces: en los 12 cambia solo un espacio sobrante en
   el asunto, y en 7 la caja de la categoría. Normalizar antes disuelve el
   conflicto. Para un conflicto que sobreviva a la normalización, **se
   conserva la captura más completa y la descartada va a cuarentena**; no se
   usó «la más reciente» porque el histórico no tiene campo de versión y el
   único orden disponible es el del archivo, que es un hecho del export y no
   del negocio.
9. **Umbral de cuarentena del 10 %** para fallar el proceso. Ajustable.

---

## Seguridad

- **Ninguna credencial en el repositorio**, ni en el historial.
  `.env.example` lleva los nombres con valores vacíos; `.env` está ignorado.
- **`INSUMOS/` no se versiona.** Además de no ser material propio,
  `pr_para_revision.diff` contiene una clave embebida: es falsa, pero un
  detector automático no distingue lo falso de lo real.
- **Consultas parametrizadas siempre.** Nunca concatenación ni el operador
  `%`, que parece parametrizado sin serlo.
- **CSV escrito con el módulo `csv`**, nunca pegando comas. Un asunto como
  «No enciende, urgente» parte una fila construida a mano y corre todas las
  columnas siguientes, en silencio.
- `ruff` (con las reglas de seguridad activas) y `bandit` corren sobre `src/`
  sin hallazgos. La única excepción documentada es `B311` en la dispersión
  del retroceso, justificada **en el punto de uso**.

---

## Decisiones documentadas

| Documento | Qué decide |
|---|---|
| [`docs/metricas.md`](docs/metricas.md) | Precisión objetivo, latencia p95 y umbrales — **definidos antes de implementar** |
| [`docs/conjunto_referencia.csv`](docs/conjunto_referencia.csv) | 58 casos etiquetados a mano, con 21 citas verificadas contra los PDF |
| [`docs/decisiones.md`](docs/decisiones.md) | Alta de dependencias, con lo descartado y su costo |
| [`docs/arquitectura.md`](docs/arquitectura.md) | Componentes, flujo extremo a extremo, datos, secretos y costo |
| [`docs/decision_requerimientos.md`](docs/decision_requerimientos.md) | R-01, R-02 y R-03: cuándo IA, cuándo automatización, y cuándo la IA estorba |
| [`docs/comparacion_enfoques.md`](docs/comparacion_enfoques.md) | Modelo clásico vs LLM, y por qué el 99 % de precisión era falso |
| [`docs/adr/ADR-001`](docs/adr/ADR-001-vectorizacion-e-indice.md) | Vectorización, índice y métrica de similitud |
| [`docs/adr/ADR-002`](docs/adr/ADR-002-orquestacion.md) | Orquestación propia, sin n8n ni framework de agentes |
| [`docs/adr/ADR-003`](docs/adr/ADR-003-fragmentacion.md) | Fragmentación por sección numerada |
| [`docs/adr/ADR-004`](docs/adr/ADR-004-desacoplamiento-proveedor-llm.md) | Desacoplamiento del proveedor y cadena de reserva |
| [`docs/adr/ADR-005`](docs/adr/ADR-005-frontera-determinista-probabilistico.md) | Qué resuelve una regla, qué un modelo, y qué se queda sin resolver |
| [`docs/adr/ADR-006`](docs/adr/ADR-006-pertinencia-de-la-cita.md) | Por qué una cita verificable no garantiza una respuesta correcta, y qué se hace con ese hueco |
| [`docs/api.md`](docs/api.md) | Qué resuelve la API, para quién, y qué **no** hace |
| [`docs/costos.md`](docs/costos.md) | Costo y latencia **medidos** contra proveedores reales, con el modelo recomendado |
| [`docs/calibracion_umbral.md`](docs/calibracion_umbral.md) | Por qué el umbral es 0.20 y por qué ningún valor cumple el 100 % |
| [`docs/informe_seguridad.md`](docs/informe_seguridad.md) | Siete hallazgos con su corrección, y cinco riesgos abiertos |
| [`docs/guia_equipo.md`](docs/guia_equipo.md) | Cómo revisar código generado por IA, con los incidentes de este proyecto |
| [`docs/revision_pr.md`](docs/revision_pr.md) | Revisión del cambio entregado: 14 hallazgos, 3 críticos |
| [`docs/declaracion_uso_ia.md`](docs/declaracion_uso_ia.md) | Las cinco preguntas, respondidas con lo que pasó |

---

## Límites

Lo que **no** quedó hecho, y por qué.

**De la etapa 1:**

- **La segunda pasada con modelo de lenguaje sobre la cuarentena está
  diseñada ([ADR-005](docs/adr/ADR-005-frontera-determinista-probabilistico.md))
  pero no implementada.** Dos razones: el pipeline debe correr en integración
  continua sin red ni credenciales, y sobre estos datos procesaría
  exactamente cero registros —no hay ni un valor fuera de catálogo—. Se
  implementa en la etapa 2, donde el adaptador ya existe.
- **La ruta de cuarentena por fecha inválida no está ejercitada por los datos
  reales.** El histórico no tiene ni una fecha malformada: 2.000 de 2.000
  convierten. Esa ruta está probada solo por las pruebas unitarias y por el
  fixture curado.
- **Las consultas SQL se verificaron en SQLite, no en MySQL.** No hay motor
  instalado en la máquina de desarrollo. El esquema carga sin modificaciones
  y las 10 sentencias corren, pero está declarado que la verificación no fue
  contra el motor de destino.
- **El tiempo promedio de atención quedó fuera de las consultas SQL** por
  portabilidad: el cálculo de días entre fechas difiere en cada motor. Está
  resuelto en Python sobre datos limpios.
- **Discrepancia no resuelta en los datos entregados:** 27 de 120 tickets del
  esquema difieren entre el contador `tickets.reaperturas` y los eventos de
  `historial_estado`. 36 tienen contador mayor que cero; solo 28 tienen
  evento. La consulta C3 devuelve ambas fuentes y marca la diferencia en vez
  de elegir una en silencio, pero **cuál es la correcta es una pregunta para
  el negocio**, no para el código.

**De la etapa 2:**

- **La API no autentica y no limita la tasa de peticiones.** Antes de
  exponerla fuera de una red controlada haría falta autenticación y
  autorización por área.
- **Las solicitudes viven en memoria y se pierden al reiniciar.** El
  almacenamiento está detrás de un puerto ([D-005](docs/decisiones.md)), así
  que pasar a SQL es escribir un adaptador, no reescribir.
- **Las claves de idempotencia no caducan.** Medido: 10.000 claves únicas
  dejan 10.000 entradas retenidas. Con persistencia real haría falta
  caducarlas y hacer única la clave en la base, porque un cerrojo de proceso
  no protege nada cuando hay varios procesos.
- **La clasificación ocurre dentro de la petición de creación**, y R-01 dice
  que *«corre en lote cada hora, no requiere respuesta inmediata»*. En
  producción convendría desacoplarla: un lote horario cuesta bastante menos.
  Se hizo síncrona para que la integración sea observable de punta a punta.
- **La clasificación se midió contra modelos reales** el 24 de agosto de 2026
  —96,5 % de exactitud con el mejor, p95 de 733 ms, $5,20 al mes con el volumen
  de R-01—; ver [`costos.md`](docs/costos.md). Una sola pasada por caso: la
  conclusión de costo es firme, la de exactitud es indicativa. Los
  identificadores de modelo de `.env.example` siguen vacíos a propósito: se
  consultan contra cada proveedor, no se ponen de memoria.
- **Las pruebas de concurrencia son red de regresión, no demostración.** Bajo
  el GIL la carrera del registro de idempotencia se reproduce 1 de cada 2
  corridas con 64 hilos, y a través del cliente de pruebas no se manifiesta
  nunca. El cerrojo está por el argumento, no por la prueba.

**De la etapa 4:**

- **La integración bidireccional está a medias.** El envío hacia el servicio
  externo existe, con tiempo de espera, reintento con retroceso e
  `Idempotency-Key`. **La recepción por webhook no está construida**: el
  mecanismo de idempotencia que necesita ya existe y está probado, pero no hay
  ruta que lo exponga. Diseñada en
  [`arquitectura.md`](docs/arquitectura.md) §4.
- **El control de costo no tiene presupuesto ni alerta.** Están el método, los
  supuestos declarados y la medición de tokens por proveedor; **faltan el
  límite máximo configurable y la alerta al superarlo**. Lo que sí está
  decidido es qué haría el sistema al superarlo, y en qué orden.

**De la etapa 3:**

- **El corpus de políticas no se valida al ingerir.** Un PDF con instrucciones
  embebidas entraría al índice y de ahí al prompt. Con el adaptador falso, toda
  consulta se abstiene en la verificación de cita — que es el comportamiento
  correcto, porque ese adaptador no cita.
- **La abstención del 100 % depende del modelo, y está medida.** Con tres
  modelos reales sobre los 6 casos sin respaldo: uno abstiene en el 100 % y
  cumple la condición dura; los otros dos se quedan en el 83 %. El caso que se
  les cuela es siempre el mismo —una pregunta sobre viáticos a una ciudad
  extranjera— y las dos puertas lo dejan pasar por construcción: el umbral no
  lo descarta porque léxicamente sí se parece, y la verificación de cita
  tampoco, porque el modelo **cita de verdad** un fragmento que recibió. La
  cita es válida; el hecho que trae no responde la pregunta. Detalle en
  [`costos.md`](docs/costos.md).
- **La suite falla el build cuando eso ocurre**, que es lo que la hace una
  barrera y no un informe: `scripts/evaluar.py` termina en 1.
- **TF-IDF no reconoce sinonimia.** Medido: «¿qué pasa si pierdo el
  computador?» no recupera su respuesta, que dice «Pérdida, hurto o daño» y
  nunca nombra el aparato. El vectorizador remoto implementa el mismo puerto
  y resolvería esto, pero no se ha conectado.
- **El corpus de políticas no se valida al ingerir.** Un PDF con
  instrucciones embebidas entraría al índice y de ahí al prompt.
- **Durante 37 ejecuciones consecutivas la integración continua estuvo en
  rojo sin que se detectara**, por un falso positivo del detector de secretos
  sobre un valor de prueba. Corregido, con el post mortem en
  [`docs/integracion_continua.md`](docs/integracion_continua.md). Lo relevante
  no es el falso positivo: es que se había dejado de correr la verificación
  completa y no se estaban leyendo las ejecuciones.
- **El costo en dinero no se estima**, solo se miden tokens y latencia. El
  precio por millón se verifica contra cada proveedor, no se pone de memoria.

**De seguridad:**

- **El texto libre del ticket no se depura antes de salir hacia el proveedor.**
  El solicitante sí: nunca se envía, y la restricción vive en el dominio. Pero
  una descripción escrita por una persona puede llevar una cédula o un teléfono
  dentro, y hoy nada lo detecta. Con datos sintéticos no importa; con datos
  reales sería lo primero que habría que construir. Declarado en
  [`declaracion_uso_ia.md`](docs/declaracion_uso_ia.md).

**Del proyecto:**

- **No se recibió la credencial del proveedor de IA prevista.** Se usan
  proveedores propios (Groq, DashScope, OpenAI) o un modelo local, y el
  criterio de la elección está declarado en
  [ADR-004](docs/adr/ADR-004-desacoplamiento-proveedor-llm.md).
**Pendientes de la entrega, no del código:**

- **La autoevaluación PC-GTH-68 no se incluye**: el formato no venía en los
  materiales entregados. Se solicita por el canal interno.

---

## Dónde está cada entregable

| Lo que pide el enunciado | Dónde |
|---|---|
| Script de limpieza, SQL, pruebas, README | `src/mai/`, [`sql/consultas.sql`](sql/consultas.sql), `tests/` |
| API propia con contrato | [`docs/api.md`](docs/api.md) · contrato generado en `/openapi.json` |
| Pantalla en Angular *(opcional con puntaje)* | [`frontend/`](frontend/README.md) |
| Módulo de IA desacoplado | [`ADR-004`](docs/adr/ADR-004-desacoplamiento-proveedor-llm.md) · `src/mai/dominio/puertos.py` |
| Defectos del legacy, rojo→verde | `legacy/legacy_module.py` · commits `8c7135d`→`ac5e48c`, `db7967d`→`b026ef4`, `bb7dcb9`→`41f75bd` |
| RAG con citas y abstención | `src/mai/rag/`, [`ADR-001`](docs/adr/ADR-001-vectorizacion-e-indice.md), [`ADR-003`](docs/adr/ADR-003-fragmentacion.md) |
| CI: ejecución exitosa y fallida | [`docs/integracion_continua.md`](docs/integracion_continua.md) |
| Informe de seguridad | [`docs/informe_seguridad.md`](docs/informe_seguridad.md) |
| Observabilidad | `GET /metricas` · `src/mai/observabilidad/` |
| Costo y latencia medidos | [`docs/costos.md`](docs/costos.md) |
| Artefacto para el equipo | [`docs/guia_equipo.md`](docs/guia_equipo.md) |
| Arquitectura y ADR | [`docs/arquitectura.md`](docs/arquitectura.md) · 6 ADR en `docs/adr/` |
| Decisión R-01/R-02/R-03 | [`docs/decision_requerimientos.md`](docs/decision_requerimientos.md) |
| Métricas previas y conjunto de referencia | [`docs/metricas.md`](docs/metricas.md) · [`conjunto_referencia.csv`](docs/conjunto_referencia.csv) |
| Suite de evaluación que falla bajo umbral | `src/mai/evaluacion/` · `scripts/evaluar.py` |
| Modelo clásico y comparación | `scripts/entrenar_clasico.py` · [`docs/comparacion_enfoques.md`](docs/comparacion_enfoques.md) |
| Revisión del cambio entregado | [`docs/revision_pr.md`](docs/revision_pr.md) |
| Declaración de uso de IA | [`docs/declaracion_uso_ia.md`](docs/declaracion_uso_ia.md) |

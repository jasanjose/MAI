# Registro de dependencias y decisiones de librería

Toda dependencia que entra al proyecto se registra aquí antes de usarse, con
cuatro cosas: **qué problema resuelve · qué se consideró · por qué esta · qué
costo se acepta.**

La pregunta previa a cualquier alta, del `CLAUDE.md` §11:

> ¿La biblioteca estándar resuelve esto en menos de treinta líneas
> comprensibles? Si sí, se escribe.

Hay una razón adicional en este proyecto: cada dependencia es superficie que
hay que poder explicar. Menos dependencias, menos preguntas sin respuesta.

**Estado actual: `dependencies = []`.** El paquete no tiene ninguna
dependencia de ejecución.

---

## D-001 · Lectura y limpieza del CSV → biblioteca estándar (`csv`)

**Problema:** leer 2.000 registros con ruido real, validarlos fila por fila,
mandar los inválidos a cuarentena **con su motivo**, deduplicar con una regla
propia y producir un resumen por área y prioridad.

| Opción | A favor | En contra |
|---|---|---|
| **`csv` (estándar)** ✅ | El procesamiento es fila a fila con decisión y motivo por fila: es exactamente el bucle de `DictReader`. Cero dependencias. Todo el valor llega como texto, que es lo que se quiere de un CSV sucio | La agregación del resumen se escribe a mano (~20 líneas) |
| `pandas` | El resumen por área y prioridad sale en dos líneas. Estándar de facto para datos tabulares | Habría que forzar `dtype=str` en todas las columnas para que las 1.299 `fecha_cierre` vacías no se conviertan en `NaN` y se confundan con ausencias reales. La cuarentena con motivo por fila es antinatural en un modelo vectorizado: obliga a máscaras booleanas y a reconstruir después por qué se cayó cada registro. Dependencia grande (con NumPy detrás) para 2.000 filas |

**Decisión:** biblioteca estándar.

Pesó más la naturaleza del problema que el tamaño del dato. Esto no es
análisis: es un proceso de saneamiento donde **cada registro rechazado tiene
que conservar su motivo**. Ese requisito es fila a fila por definición, y
pandas es la herramienta contraria a fila a fila.

El volumen tampoco lo justifica: 2.000 filas es un `for` en milisegundos.

> Esta decisión **cambia lo que decía el plan inicial**, que había elegido
> pandas por inercia («estándar, maneja el volumen»). Al llegar al diseño de
> la cuarentena quedó claro que el argumento del volumen no aplica a esta
> escala y que el modelo vectorizado estorba al requisito real.

**Costo aceptado:**
- La agregación del resumen se escribe a mano. Son ~20 líneas y hay que
  probarlas; con pandas serían dos líneas ya probadas por terceros.
- Si más adelante hace falta análisis exploratorio de verdad —correlaciones,
  ventanas móviles, pivotes— habrá que traer pandas igual. Este proyecto no
  lo necesita; el cuaderno del modelo clásico de la etapa 5 sí, y ahí se
  evaluará por separado.
- No hay lectura por bloques. Si el archivo creciera a millones de filas,
  este enfoque carga todo en memoria y habría que rehacerlo.

**Se revisaría si:** el volumen sube dos órdenes de magnitud, o si aparece
necesidad de análisis tabular real más allá de contar y agrupar.

---

## D-002 · Pruebas → `pytest` *(solo desarrollo)*

**Problema:** pruebas legibles, con parametrización, ejecutables en CI.

| Opción | A favor | En contra |
|---|---|---|
| **`pytest`** ✅ | `assert` plano sin métodos de aserción. `parametrize` convierte doce casos en una prueba. Estándar en el ecosistema | Dependencia externa, aunque solo de desarrollo |
| `unittest` (estándar) | Cero dependencias | Más ceremonia: clases, `self.assertEqual`, sin parametrización nativa cómoda |

**Decisión:** `pytest`. La parametrización se usa de inmediato —los doce
meses en español son una sola prueba— y la legibilidad de las pruebas es
parte de lo que se evalúa.

**Costo aceptado:** una dependencia de desarrollo. No entra al paquete
publicado: vive en `[project.optional-dependencies].dev`.

---

## D-003 · Análisis estático → `ruff` + `bandit` *(solo desarrollo)*

**Problema:** detectar en cada guardado y en cada envío lo que una revisión
humana deja pasar, con énfasis en seguridad del código generado por IA.

**Decisión:** ambos, y `ruff` con la familia `S` activada, que replica buena
parte de lo que `bandit` detecta. Se corren los dos porque cubren cosas
distintas y porque el informe de seguridad de la etapa 3 cita la salida de
`bandit` como evidencia verificable.

**Costo aceptado:** dos herramientas con solapamiento parcial. Se acepta
porque `bandit` sobre el diff a revisar produce evidencia citable que `ruff`
solo no da.

**No sustituyen la revisión humana: la enfocan.**

---

## D-004 · API propia → `fastapi` + `uvicorn` + `pydantic`

**Qué problema resuelve.** La etapa 2 pide una API REST con tres recursos,
validación de entrada, códigos de estado correctos, una forma uniforme de
error y **el contrato de la API como entregable**.

| Opción | A favor | En contra |
|---|---|---|
| **`fastapi` + `uvicorn` + `pydantic`** | Genera el contrato OpenAPI **desde el propio código**. Validación declarativa con errores estructurados. `uvicorn` es el servidor; `pydantic` ya viene como dependencia de `fastapi` y se declara explícita porque se usa directamente | Tres dependencias. Los errores de validación traen la forma de `pydantic` y hay que traducirlos a la nuestra: eso es trabajo real, no gratis |
| `flask` | Una sola dependencia, muy conocido | Validación a mano y sin contrato generado. Acabaría siendo `flask` más una librería de validación: dos dependencias y más código propio que mantener |
| `http.server` (estándar) | Cero dependencias | Enrutado, análisis del cuerpo, validación y errores JSON escritos a mano. No cabe en «treinta líneas comprensibles», y ese servidor no está pensado para servir nada real |

**Por qué esta.** El argumento decisivo no es la comodidad sino la
**consistencia entre el contrato y la implementación**. Un contrato escrito a
mano en un Markdown queda obsoleto en el primer cambio de la API y nadie se
entera hasta que un consumidor falla. Generado desde el código, no puede
desviarse.

`uvicorn` entra porque una aplicación ASGI necesita un servidor que la
ejecute; no aporta funcionalidad propia al código.

**Qué costo se acepta.**

- Tres dependencias de ejecución donde antes había una.
- `pydantic` valida y produce sus propios errores. Traducirlos a
  `{codigo, mensaje, detalle, id_traza}` es código que hay que escribir y
  probar; sin esa traducción la API tendría dos formas de error distintas.
- El proyecto queda atado al ecosistema ASGI. Migrar a otro marco exigiría
  reescribir la capa `api/`, aunque no el dominio.

**Qué NO se adopta.** No entra ORM. Las solicitudes viven en memoria detrás
de un puerto (ver D-005): cambiar a SQL será un adaptador nuevo, no una
reescritura.

---

## D-005 · Persistencia de solicitudes → puerto + adaptador en memoria

**Qué problema resuelve.** La API necesita guardar y consultar solicitudes.

| Opción | A favor | En contra |
|---|---|---|
| **Puerto en el dominio + adaptador en memoria** | Cero dependencias. Las pruebas corren sin base de datos y sin red. El puerto hace que pasar a SQL sea un adaptador nuevo, no una reescritura | **Los datos se pierden al reiniciar.** No sirve para producción y hay que declararlo |
| `sqlite3` (estándar) | Persiste, cero dependencias, consultas parametrizadas reales | El esquema entregado es de sabor MySQL y adaptarlo es trabajo. La evidencia de SQL parametrizado ya está en `sql/consultas.sql` |
| MySQL con conector | Coincide con el esquema entregado | Necesita un servidor corriendo: rompe la regla de que las pruebas no dependan de red ni de infraestructura |

**Por qué esta.** Es el mismo argumento que se aplicó al proveedor de
lenguaje: el dominio depende de una abstracción y la implementación concreta
se elige al componer. Lo que se gana no es simplicidad, es **poder cambiar de
almacenamiento sin tocar la lógica**.

**Qué costo se acepta.** Los datos no sobreviven a un reinicio. Se declara en
el README como límite, no se disimula. Con más tiempo, el siguiente adaptador
es `sqlite3` sobre el esquema entregado.

---

## Decisiones pendientes

Analizadas, sin aprobar todavía. Ninguna se usa hasta que se decida.

### P-001 · Cliente HTTP para el servicio mock *(etapa 1)*

Se necesita: tiempo de espera explícito, reintento con retroceso exponencial,
lectura de la cabecera `Retry-After` en las respuestas 429 y acceso limpio al
código de estado.

| Opción | A favor | En contra |
|---|---|---|
| `httpx` | Timeouts explícitos por diseño. **Cubre síncrono y asíncrono con una sola dependencia** — la etapa 2 monta una API asíncrona que también llama al proveedor de IA | Dependencia externa |
| `requests` | El más conocido | Solo síncrono. En la etapa 2 habría que sumar otra librería |
| `urllib.request` (estándar) | Cero dependencias. Tiene `timeout` | Los errores llegan como excepción `HTTPError` que además es la respuesta; leer `Retry-After` de ahí es incómodo. El código resultante es más largo y menos claro que el problema que resuelve |

**Recomendación:** `httpx`. El argumento decisivo no es la comodidad sino que
**una sola dependencia sirve para las etapas 1 y 2**; con `requests` habría
que traer una segunda al llegar a la API asíncrona.

Aquí la biblioteca estándar sí resuelve, pero **no en menos de treinta líneas
comprensibles**: el manejo de errores de `urllib` es justamente donde se
esconden los defectos.

### P-002 · Extracción de texto de PDF *(etapa 3)*
### P-003 · Modelo de embeddings y base vectorial *(etapa 3 — va a ADR-001)*
### P-004 · API propia *(etapa 2)* — **resuelta, ver D-004**
### P-005 · Modelo clásico y matriz de confusión *(etapa 5)*

# Arquitectura

Documento de diseño de MAI. Describe **lo que está construido** y **lo que
está diseñado sin construir**, y los distingue en cada sección: mezclarlos
haría el documento inservible para quien tenga que continuarlo.

---

## 1 · Componentes

```
                      ┌──────────────────────────────────────┐
   HTTP               │              api/                    │
  ────────────────────▶  rutas · esquemas · errores · traza  │
                      └───────────────┬──────────────────────┘
                                      │ traduce HTTP ↔ dominio
                                      │ NO contiene reglas de negocio
                      ┌───────────────▼──────────────────────┐
                      │            dominio/                  │
                      │                                      │
                      │  solicitudes   clasificacion         │
                      │  politicas     catalogos  fechas     │
                      │                                      │
                      │  puertos:  ProveedorLLM              │
                      │            RepositorioSolicitudes    │
                      │            RegistroDeIdempotencia    │
                      │            RecuperadorDeFragmentos   │
                      │            Vectorizador              │
                      └──┬────────────┬───────────┬──────────┘
                         │            │           │   ▲ el dominio NO importa
                         │            │           │   │ nada de abajo
       ┌─────────────────▼──┐  ┌──────▼──────┐  ┌─▼───────────────┐
       │  adaptadores/llm/  │  │adaptadores/ │  │      rag/       │
       │                    │  │persistencia/│  │                 │
       │  falso             │  │             │  │  ingesta        │
       │  compatible ───────┼──┤ memoria     │  │  vectorizacion  │
       │  enrutador         │  │ idempotencia│  │  indice         │
       │  fabrica           │  │             │  │  fabrica        │
       └────────┬───────────┘  └─────────────┘  └─────────────────┘
                │                                        │
                ▼                                        ▼
        proveedor de lenguaje                   PDF de politicas
        (Groq · OpenAI · …)                     (no versionados)

       ┌────────────────────────┐      ┌──────────────────────────┐
       │ adaptadores/http/      │      │    observabilidad/       │
       │ cliente del servicio   │      │  traza · registro JSON   │
       │ externo simulado       │      │  metricas agregadas      │
       └────────────────────────┘      └──────────────────────────┘
```

**La regla que sostiene todo:** `dominio/` no importa `adaptadores/`, `api/`,
`rag/`, ni ninguna librería de infraestructura. Es verificable en un segundo:

```bash
grep -rE "^(from|import)" src/mai/dominio/ | grep -E "adaptador|httpx|fastapi|pypdf"
# (vacío)
```

Esa regla es lo que hace que cambiar de proveedor sea cambiar una variable de
entorno, y lo que permite que las 488 pruebas corran sin red ni credenciales.

---

## 2 · Flujo extremo a extremo

### Crear una solicitud · `POST /solicitudes` · **construido**

```
cliente
  │ POST {asunto, descripcion, area, solicitante}   [Idempotency-Key opcional]
  ▼
middleware de traza ─── fija id_traza (del cliente o generado)
  ▼
pydantic ─────────────── forma y cotas    → 422 si no cumple · 400 si no es JSON
  ▼
registro de idempotencia
  ├── clave repetida, mismo contenido → devuelve el recurso ya creado (201 + Replayed)
  ├── clave repetida, otro contenido  → 409
  └── clave nueva → reserva
  ▼
ServicioSolicitudes.crear
  ├── valida area/canal contra catalogo cerrado  → 422
  ├── Clasificador.clasificar(asunto, descripcion)      ← NO recibe solicitante
  │     ├── prompt: instruccion (system) + ticket delimitado (user)
  │     ├── EnrutadorLLM: proveedor 1 → 2 → … → CadenaAgotada
  │     ├── valida la salida contra las 12 categorias
  │     └── si algo falla → reglas por palabras clave, marcado degradado
  └── guarda con codigo SOL-NNNNNN
  ▼
metricas ─────────────── clasificacion, latencia, tokens
registro JSON ────────── id_traza, codigo, area, categoria — sin contenido
  ▼
201 {codigo, categoria, prioridad, origen_clasificacion, confianza, motivo}
```

**La clasificación nunca impide la creación.** Si el proveedor cae, la
solicitud se crea igual, marcada `degradado`/`baja`. Dejar caer el trabajo de
un usuario por un fallo nuestro sería cambiar un problema de calidad por uno
de pérdida de datos.

### Consultar una política · `POST /consultas` · **construido**

```
cliente
  │ POST {pregunta}
  ▼
IndiceEnMemoria.buscar(pregunta, k=5)      coseno sobre 67 fragmentos
  ▼
PUERTA 1 · ¿mejor puntaje ≥ 0.20?
  └── no → ABSTENCION  (sin llamar al modelo: no se paga por improvisar)
  ▼
prompt: fragmentos con su cita (system) + pregunta delimitada (user)
  ▼
EnrutadorLLM ── cadena RUTA_RAG ── si se agota → ABSTENCION (nunca reglas)
  ▼
PUERTA 2 · ¿la respuesta cita, y las citas estaban entre los fragmentos dados?
  ├── no cita               → ABSTENCION
  ├── cita algo no entregado → ABSTENCION
  └── sí → respuesta con sus citas
  ▼
200 {respuesta, citas, origen, motivo, fragmentos_consultados, mejor_puntaje}
```

---

## 3 · Orquestación

**Decidido en [ADR-002](adr/ADR-002-orquestacion.md): implementación propia.**
El flujo es una secuencia lineal con una bifurcación condicional —clasificar,
recuperar, redactar, o escalar—. No tiene ciclos, ni ramas paralelas que
converjan, ni pausas a la espera de intervención humana dentro de la misma
ejecución.

Un motor visual o un framework de agentes resuelven grafos que aquí no
existen, y meterían la lógica de conmutación y degradado —que es el núcleo
del diseño— dentro de una caja que habría que entender igual para operarla.

**Construido:** la secuencia de clasificación y la de consulta, cada una en su
servicio de dominio. **Diseñado, no construido:** encadenar las dos —clasificar
una solicitud, y si es una consulta de política responderla con RAG en el
mismo flujo— y el escalamiento automático a una persona cuando la confianza es
baja.

---

## 4 · Integración bidireccional · **diseñado, parcialmente construido**

El segundo sistema es el servicio externo simulado. La mitad de salida existe;
la de entrada no.

### Salida — **construido**

`adaptadores/http/cliente_solicitudes.py` con tiempo de espera explícito,
reintento con retroceso exponencial respetando `Retry-After`, traducción de
errores a lenguaje del dominio, y soporte de `Idempotency-Key`.

**Por qué la clave importa aquí más que en nuestra API:** este cliente
reintenta. Un `500` devuelto *después* de que el servicio ya creó el registro
produciría un duplicado en el reintento. La clave es lo que hace que reintentar
sea seguro.

### Entrada por webhook — **diseñado, no construido**

```
sistema externo ──POST /webhook/mensajeria──▶ MAI
                    │  Idempotency-Key
                    ▼
              ¿clave ya vista?
                 sí → 200 con el resultado anterior, sin reprocesar
                 no → reserva atómica → procesa → completa
```

La pieza que falta es la ruta; el mecanismo ya existe y está probado
—`dominio/idempotencia.py` y su registro—. El diseño reutiliza el mismo
`reservar/completar/liberar`.

### Estado coherente en ambos extremos

Con dos sistemas y reintentos, la coherencia no se logra con una transacción
distribuida sino con **operaciones repetibles sin efecto en los dos sentidos**:
cada lado acepta una clave de idempotencia y devuelve el resultado anterior en
vez de rehacer. Es la razón de que el mecanismo esté en el dominio y no en la
capa HTTP: sirve para las dos direcciones.

---

## 5 · Diseño de datos

### Relacional · **diseñado, no construido**

Hoy las solicitudes viven en memoria detrás de `RepositorioSolicitudes`
([D-005](decisiones.md)). El modelo de destino parte del esquema entregado y le
añade lo que la trazabilidad exige:

| Tabla | Para qué | Nota |
|---|---|---|
| `areas`, `usuarios`, `tickets`, `adjuntos`, `historial_estado` | Del esquema entregado | Sin cambios |
| `clasificaciones` | Una fila por intento: proveedor, modelo, origen, confianza, motivo, tokens, latencia | **Sin esto no se puede auditar por qué un ticket quedó en una categoría** |
| `claves_idempotencia` | clave, huella del contenido, recurso creado, momento | `UNIQUE(clave)` — la indivisibilidad la da la base, no un cerrojo de proceso |

**Índices propuestos** (el esquema entregado no trae ninguno, a propósito):
están justificados en [`sql/consultas.sql`](../sql/consultas.sql), junto con
**qué no se indexa y por qué** — `categoria`, `prioridad` y `canal` tienen 12,
4 y 4 valores distintos, y indexar baja cardinalidad es costo de escritura sin
beneficio de lectura.

**El día que esto se implemente, el cerrojo de idempotencia deja de servir:**
con varios procesos sirviendo la API, un cerrojo local no protege nada. Ese es
el punto donde `UNIQUE(clave)` pasa de ser una mejora a ser la única garantía.

### Vectorial · **construido**

Decidido en [ADR-001](adr/ADR-001-vectorizacion-e-indice.md) y
[ADR-003](adr/ADR-003-fragmentacion.md), con las tres justificaciones que el
diseño exige explícitas:

| | Decisión | Por qué |
|---|---|---|
| **Tamaño de fragmento** | La sección numerada más fina. ~25 palabras medidas | El número de sección **es la cita**, y sale de la estructura, no de una heurística |
| **Modelo de embeddings** | TF-IDF propio por defecto; remoto tras el mismo puerto | Corre sin red ni credenciales. La sinonimia es el costo declarado y está medido |
| **Métrica de similitud** | Coseno | Mide dirección y no magnitud: un fragmento largo no gana por largo. Con vectores normalizados, es el producto punto |

**Sin base vectorial.** 67 fragmentos son 67 productos punto. Se revisaría a
partir de unos miles, o si hiciera falta persistir el índice.

---

## 6 · Secretos y ambientes

**Construido.** Ninguna credencial en el repositorio, ni en el historial:
verificado en cada envío por el trabajo `secretos` del flujo, que revisa los
archivos versionados, **el historial completo** (`fetch-depth: 0`) y las rutas
privadas.

`.env.example` versionado con los nombres y valores vacíos; `.env` ignorado.
Las URL base que no se pueden afirmar se dejan vacías con una nota: una
configuración de ejemplo con un valor equivocado cuesta más que una con el
hueco declarado — el hueco se ve, el valor equivocado se copia.

**Separación de ambientes, diseñada:**

| | `RUTA_*` | Corpus | Persistencia |
|---|---|---|---|
| **CI** | `falso` | fixture propio | memoria |
| **Desarrollo** | proveedor barato | copia local | memoria |
| **Producción** | cadena con reserva | volumen montado | base de datos |

La misma imagen en los tres; solo cambian variables de entorno. En producción
las credenciales vendrían de un gestor de secretos y no de un `.env` — eso
**no está construido**.

---

## 7 · Control de costo · **diseñado, parcialmente construido**

**Construido:** cada llamada reporta tokens de entrada y salida, y `/metricas`
los agrega por proveedor. Los tokens ausentes se cuentan aparte y **nunca como
cero**: sumar ceros haría parecer que el sistema consume menos de lo que
consume, y esa es justo la métrica que se usa para presupuestar.

**No construido, y declarado:** la estimación en dinero. Exige el precio por
millón de tokens de cada proveedor, que se consulta contra su documentación.
**Un costo inventado es peor que ninguno**, porque se usaría para decidir.

### Cómo se estimaría, con los supuestos declarados

De R-01 y R-02: 3.000 clasificaciones y 80 consultas de política al día.

| | Entrada estimada | Salida | Volumen mensual |
|---|---:|---:|---:|
| Clasificación | ~250 tokens (prompt + ticket) | ~20 | 90.000 llamadas |
| Consulta RAG | ~900 tokens (5 fragmentos + pregunta) | ~120 | 2.400 llamadas |

```
clasificacion:  90.000 × 270  ≈ 24,3 M tokens/mes
RAG:             2.400 × 1.020 ≈  2,4 M tokens/mes
```

**Los supuestos son lo que hay que revisar, no el resultado:** 250 tokens por
ticket sale de medir los del histórico, pero el prompt puede crecer; y los
90.000 asumen que se clasifica cada solicitud una vez, sin reintentos ni
reprocesos.

**Qué haría el sistema al superar el presupuesto —diseñado—:** degradar la
clasificación a reglas antes que dejar de recibir solicitudes, y **nunca
degradar el RAG a reglas**: ahí el modo degradado es abstenerse. El orden no
es arbitrario — clasificar mal cuesta un minuto de un analista; responder mal
sobre un plazo cuesta una reclamación formal.

---

## 8 · Escalabilidad y mantenibilidad

**Lo que escala sin tocar el diseño:** cambiar de proveedor o añadir uno
(una línea y tres variables); pasar de memoria a SQL (un adaptador nuevo);
cambiar TF-IDF por embeddings (otro adaptador del mismo puerto).

**Lo que no escala y hay que rehacer, declarado:**

| Límite | Cuándo aparece | Qué habría que hacer |
|---|---|---|
| Datos en memoria | Al primer reinicio | Adaptador SQL |
| Cerrojo de idempotencia | Con más de un proceso | `UNIQUE(clave)` en la base |
| Claves sin caducidad | Con persistencia real | Caducidad a 24 h |
| Índice reconstruido al arrancar | Con miles de fragmentos | Persistirlo |
| Búsqueda exacta | Con miles de fragmentos | Índice aproximado |
| Clasificación dentro del `POST` | Con carga alta | Desacoplar a lote — **R-01 ya lo pide** |
| Sin autenticación | Antes de exponerla | Autenticación y autorización por área |

**El último es el más urgente**, y no depende del volumen.

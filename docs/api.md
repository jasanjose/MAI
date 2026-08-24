# API de solicitudes — documentación funcional

> El **contrato técnico** no se escribe a mano: se genera del código y se
> publica en `/openapi.json`, con navegador en `/docs`. Este documento cubre
> la otra mitad —qué resuelve, para quién, y qué **no** hace—, que es lo que
> un contrato generado no puede decir.

---

## Qué problema resuelve

El área de Aplicaciones recibe solicitudes internas escritas en texto libre,
por correo y por formulario. Antes de poder atenderlas hay que decidir de qué
son y qué tan urgentes, y eso lo hace hoy una persona leyendo cada una.

Esta API recibe la solicitud, **le asigna categoría y prioridad**, y la deja
consultable. El objetivo no es acertar siempre: es que el analista reciba las
solicitudes ya ordenadas y corrija las que estén mal, en lugar de clasificar
las 3.000 desde cero.

## Para quién

| Quien la usa | Para qué |
|---|---|
| **El formulario interno y el buzón de correo** | Registran cada solicitud que entra, sin intervención humana |
| **El analista de la mesa de ayuda** | Consulta y filtra lo que le toca por área, prioridad o estado |
| **Quien reporta** | Consulta el estado de su solicitud con el código que recibió |

## Qué hace: tres operaciones de negocio y dos de operación

**Registrar una solicitud.** Se envía asunto, descripción, área y quién
reporta. Devuelve un código —`SOL-000001`— con el que se consulta después.

**Consultar una solicitud.** Por su código. Devuelve su estado actual y cómo
quedó clasificada.

**Listar con filtros.** Por área, estado, categoría y prioridad, con
paginación. Las más recientes primero.

Aparte de las tres, hay dos operaciones que no son del negocio sino de quien
opera el sistema:

**`GET /salud`.** Si está en pie, con qué proveedor quedó configurada cada
tarea y cuántos fragmentos de política tiene indexados. Ese último número es el
que delata una configuración mal puesta: **un cero ahí significa que la ruta al
corpus está mal**, y el sistema arranca igual porque fallar al arrancar
tumbaría también la parte que sí funciona.

**`GET /metricas`.** Lo acumulado desde que arrancó el proceso:

| Grupo | Qué trae |
|---|---|
| `operaciones` | latencia p50/p95/p99 y cuenta, por ruta |
| `clasificacion` | total, cuántas degradadas, y **el desglose por motivo** |
| `consultas` | total, cuántas abstenidas, y por qué motivo |
| `proveedor_llm` | llamadas, tokens de entrada y salida, y **cuántos de salida fueron razonamiento** |

Tres decisiones que conviene entender al leerla:

**El desglose por motivo es lo que la hace accionable.** Un proveedor caído y un
modelo que devuelve basura degradan igual y exigen acciones opuestas. Sin el
motivo, la tasa dice que algo va mal y no qué.

**Los tokens ausentes no se cuentan como cero.** Van aparte, en
`llamadas_sin_tokens_reportados`. Sumar ceros haría parecer que el sistema
consume menos de lo que consume, y esa es justo la cifra que se usa para
presupuestar.

**`tokens_razonamiento` no se suma al total**: ya viene dentro de
`tokens_salida`. Está separado porque es lo único que distingue un modelo
verboso de uno que razona de más — y solo el segundo se arregla apagando un
ajuste, sin cambiar de modelo.

`costo_estimado` viene en `null` a propósito: exige el precio por millón de cada
proveedor, que se consulta contra su consola y no se pone de memoria. Las cifras
medidas están en [`costos.md`](costos.md).

---

## Tres cosas que conviene entender antes de usarla

### 1 · La clasificación puede venir de dos sitios, y la respuesta lo dice

Cada solicitud trae dos campos que no son decorado:

```json
{ "origen_clasificacion": "modelo",     "confianza": "alta" }
{ "origen_clasificacion": "degradado",  "confianza": "baja",
  "motivo_degradacion": "proveedor_no_disponible" }
```

Cuando el proveedor de lenguaje no responde, o responde algo que no está en
el catálogo, **la solicitud se crea igual** con una clasificación por reglas
de palabras clave. Nunca se pierde el trabajo de quien reporta por un fallo
nuestro.

Pero una clasificación degradada acierta menos. **Quien consume la API debe
mirar esos campos** para decidir si la usa directamente o la manda a
revisión. Tratar las dos igual es el error más probable al integrarse.

`motivo_degradacion` distingue causas que exigen acciones opuestas: un
proveedor caído se resuelve esperando; un modelo que devuelve valores fuera
del catálogo se resuelve cambiando el modelo o el prompt.

### 2 · Reintentar sin duplicar: `Idempotency-Key`

Si la respuesta se pierde en la red, el cliente no sabe si la solicitud se
creó. Reintentar sin protección crea una segunda.

Envíe una clave única por operación:

```http
POST /solicitudes
Idempotency-Key: 8f7c2a91-4b1e-4d3a-9c22-0f1a2b3c4d5e
```

Repetir la petición **con la misma clave y el mismo contenido** devuelve la
solicitud original en lugar de crear otra, y marca la respuesta:

```http
201 Created
Idempotency-Replayed: true
```

El estado sigue siendo `201` las dos veces: describe el resultado de la
operación, y la operación creó el recurso.

**La misma clave con otro contenido devuelve `409`.** No es un reintento: es
un error del cliente, y devolverle la solicitud original le haría creer que
registró algo distinto de lo que existe.

La clave es opcional. Sin ella no hay deduplicación: dos peticiones idénticas
son dos solicitudes, porque puede que de verdad haya dos problemas iguales.

### 3 · Todos los errores tienen la misma forma

```json
{
  "codigo": "VALIDACION_ENTRADA",
  "mensaje": "El campo «area» es obligatorio y debe ser un área conocida.",
  "detalle": { "campo": "area" },
  "id_traza": "e3f44a9e3ed446af84d3f2a878742795"
}
```

| Código HTTP | Cuándo | Qué hacer |
|---:|---|---|
| `400` | El cuerpo no es JSON | Revisar el serializador del cliente |
| `422` | Es JSON pero el contenido no cumple | Revisar los datos; `detalle.campo` dice cuál |
| `404` | El código de solicitud no existe | Verificar el código |
| `409` | La clave de idempotencia ya se usó con otro contenido, u otra petición con esa clave está en curso | Usar otra clave, o esperar y consultar |
| `500` | Algo no previsto | Reportar el `id_traza` |

**El `id_traza` viaja en todas las respuestas**, en la cabecera `X-Id-Traza` y
dentro del cuerpo de error. Es lo que permite que quien reporta un problema
dé un identificador y quien lo investiga encuentre esa petición exacta. Si su
sistema ya maneja uno, envíelo en `X-Id-Traza` y se conserva.

---

## Qué NO hace

Declarado a propósito. Un límite conocido es información útil; uno oculto es
una falla esperando a producción.

- **No autentica.** Cualquiera que alcance la red puede crear y consultar
  solicitudes. Antes de exponerla fuera de una red controlada hace falta
  autenticación y autorización por área.
- **No limita la tasa de peticiones.** El `429` que el sistema sabe manejar
  es el que recibe de servicios externos, no uno que emita.
- **No persiste.** Las solicitudes viven en memoria y **se pierden al
  reiniciar el proceso**. La decisión y su alternativa están en
  [`decisiones.md`](decisiones.md) D-005: el almacenamiento está detrás de un
  puerto, así que pasar a SQL es escribir un adaptador, no reescribir.
- **Las claves de idempotencia no caducan.** Se conservan mientras el proceso
  viva. Con persistencia real haría falta caducarlas —24 horas es lo
  habitual— y hacer única la clave en la base de datos, porque un cerrojo de
  proceso no protege nada cuando hay varios procesos.
- **No permite cambiar el estado de una solicitud.** Toda nace `Abierto`. No
  hay operación de cierre ni de reasignación.
- **No adjunta archivos**, aunque el modelo de datos relacional los contemple.
- **Clasifica dentro de la petición de creación.** El requerimiento R-01 dice
  que la clasificación *«corre en lote cada hora, no requiere respuesta
  inmediata»*, así que en producción convendría desacoplarla: un lote horario
  cuesta bastante menos y no hace esperar a quien registra. Se hizo síncrona
  para que la integración sea observable de punta a punta.

---

## Cómo se ejecuta

```bash
pip install -e ".[dev]"
python -m mai.api                       # 127.0.0.1:8000
uvicorn mai.api.main:app --port 8000    # equivalente
```

Sin variables de entorno funciona: las dos rutas de proveedor caen en `falso`,
un adaptador determinista que no usa red. **Toda solicitud saldrá entonces con
`origen_clasificacion: "degradado"`**, porque el adaptador falso no devuelve
clasificaciones reales. Para usar un proveedor de verdad, ver
[`.env.example`](../.env.example).

`GET /salud` responde qué cadena está configurada — diagnostica el problema
más frecuente al desplegar: creer que se apuntó a un proveedor real y estar
corriendo contra el falso.

```bash
curl -X POST localhost:8000/solicitudes \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: mi-clave-unica-1' \
  -d '{"asunto":"No puedo entrar al sistema de nómina",
       "descripcion":"Me pide la contraseña y la rechaza",
       "area":"Talento Humano",
       "solicitante":"usuario001@lafortuna.com.co"}'
```

---

## Catálogos cerrados

La API valida contra catálogos cerrados y rechaza lo que no esté en ellos. Un
filtro con un valor desconocido devuelve `422`, no una lista vacía: responder
`[]` a `estado=cerado` haría creer que no hay solicitudes cerradas.

| Campo | Valores |
|---|---|
| **Área** | Aplicaciones · Infraestructura · Talento Humano · Contabilidad · Compras · Comercial · Operaciones · Calidad |
| **Categoría** | Accesos · Capacitación · Compras · Hardware · Incidentes · Informes · Nómina · Otros · Red · Software · Vacaciones · Viáticos |
| **Prioridad** | Crítica · Alta · Media · Baja |
| **Estado** | Abierto · En proceso · Cerrado · Reabierto · Escalado |
| **Canal** | Correo · Teléfono · Formulario · Mesa de ayuda |

Los valores se normalizan al recibirlos: `talento humano`, `TALENTO HUMANO` y
`  Talento Humano  ` son el mismo área.

---

## Qué datos salen del sistema

Al proveedor de lenguaje viajan **solo el asunto y la descripción**. Nunca el
solicitante, su correo ni el código de la solicitud. La garantía no es una
lista de campos que se borran: la función que clasifica **no recibe** el
solicitante, y lo que no entra no se puede filtrar por descuido.

Los registros del servidor llevan identificadores y medidas —código, área,
categoría, latencia— y **nunca el contenido del ticket ni datos personales**.

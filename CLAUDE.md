# CLAUDE.md — Estándar de ingeniería · MAI (Mesa de Ayuda Inteligente)

Estándar técnico del proyecto. Aplica a todo el código de este repositorio,
lo escriba una persona o un asistente de IA.

> **Sobre el uso de asistentes de IA en este proyecto:** está permitido y es
> parte del método de trabajo. Lo que este documento fija es el criterio con
> que se usan y las condiciones que debe cumplir el resultado —
> independientemente de quién lo haya escrito. El uso queda declarado en
> [`docs/declaracion_uso_ia.md`](docs/declaracion_uso_ia.md).

---

## 1. Principios

1. **Todo el código de este repositorio es responsable por su autor.** Quien
   lo integra debe poder explicarlo y modificarlo. Código que nadie puede
   explicar no se integra, sin importar que funcione.
2. **El escenario feliz no es el criterio de aceptación.** Una función se
   considera terminada cuando está definido y probado qué hace con la
   entrada inválida, vacía o corrupta.
3. **Lo que no se mide no se puede sostener.** Toda llamada a un servicio
   externo reporta latencia y costo.
4. **Ante la duda, abstenerse.** Un sistema que dice «no tengo evidencia»
   vale más que uno que responde siempre.
5. **Una decisión sin alternativa descartada no es una decisión.**

---

## 2. Estructura

```
src/mai/
├── dominio/          # Lógica de negocio. Sin dependencias de infraestructura.
├── adaptadores/
│   ├── llm/          # Proveedores de IA (intercambiables)
│   ├── http/         # Clientes de servicios externos
│   └── persistencia/
├── api/              # Capa HTTP: rutas, esquemas, manejadores de error
├── rag/              # Ingesta, fragmentación, recuperación
└── observabilidad/   # Métricas, registro estructurado
tests/
├── fixtures/         # Datos de prueba versionados
docs/                 # Documentos de decisión y entregables
sql/                  # Consultas
```

**Regla de dependencias:** `dominio/` no importa nada de `adaptadores/`,
`api/` ni librerías de terceros que representen infraestructura. La
dirección de dependencia siempre apunta hacia el dominio.

---

## 3. Proveedores de IA — desacoplamiento obligatorio

La lógica de negocio **nunca** llama a un proveedor directamente.

```python
# ✅ Correcto — el dominio depende de una abstracción
from mai.dominio.puertos import ProveedorLLM

class Clasificador:
    def __init__(self, proveedor: ProveedorLLM) -> None:
        self._proveedor = proveedor
```

```python
# ❌ Incorrecto — acopla el negocio a un proveedor concreto
import openai

class Clasificador:
    def clasificar(self, texto: str) -> str:
        return openai.chat.completions.create(...)
```

**Criterio de aceptación:** cambiar de proveedor debe ser cambiar la variable
de entorno `PROVEEDOR_LLM`. Cero líneas de código. Si hay que tocar el
dominio, el diseño está mal.

Implementaciones disponibles:

| Valor | Adaptador | Uso |
|---|---|---|
| `falso` | Determinista, sin red | Pruebas, CI, desarrollo sin credencial |
| `openai` | Proveedor remoto | Producción |
| `ollama` | Modelo local | Alternativa sin credencial externa |

El adaptador `falso` **no es un stub de conveniencia**: permite que la suite
completa corra en CI sin credenciales, sin red y de forma reproducible.

### Todo adaptador debe implementar

- **Tiempo de espera explícito.** Ninguna llamada de red sin `timeout`.
- **Reintento con retroceso exponencial**, respetando `Retry-After` cuando
  el servicio lo envía.
- **Modo degradado.** Si el proveedor no responde tras los reintentos, el
  sistema responde con la ruta alternativa y marca la salida como
  `origen: "degradado"`, `confianza: "baja"`. Nunca propaga una excepción
  cruda al usuario.
- **Reporte de latencia y tokens** por llamada.

---

## 4. Manejo de errores

Toda función que procese datos externos define su comportamiento ante:
entrada vacía · entrada malformada · tipo inesperado · valor fuera de rango ·
servicio no disponible.

**Los registros inválidos van a cuarentena con su motivo. No se descartan en
silencio.** Todo proceso por lotes emite un reporte de calidad: cuántos
entraron, cuántos salieron, cuántos a cuarentena y por qué.

```python
# ✅ El motivo se conserva
if fecha is None:
    cuarentena.registrar(fila, motivo="fecha_no_reconocida")
    continue
```

```python
# ❌ El dato desaparece sin rastro
try:
    fecha = parsear(valor)
except Exception:
    pass
```

Errores de la API con **forma uniforme** en toda la superficie:

```json
{ "codigo": "VALIDACION_ENTRADA", "mensaje": "...", "detalle": {}, "id_traza": "..." }
```

Nunca se devuelve una traza de excepción al cliente. Los códigos de estado
se usan según su significado: `400` petición malformada · `422` semántica
inválida · `404` no existe · `429` límite de tasa · `502` falla del
proveedor externo · `500` solo lo no previsto.

---

## 5. Seguridad

### 5.1 Secretos

- **Ninguna credencial en el repositorio.** Ni en código, ni en
  configuración, ni en pruebas, ni en documentación, ni en el historial de
  Git.
- Toda configuración sensible por variable de entorno.
- `.env.example` versionado con los **nombres** de las variables y valores
  vacíos. `.env` en `.gitignore`.
- Al citar credenciales en documentación (por ejemplo en una revisión de
  código), se redactan: `sk-proj-****REDACTADO****`.

Un secreto que estuvo versionado **sigue en el historial** aunque se borre
después. Se previene, no se corrige.

### 5.2 Consultas a base de datos

**Siempre parametrizadas. Sin excepción.**

```python
# ✅
cursor.execute("SELECT * FROM tickets WHERE id_area = %s", (id_area,))
```

```python
# ❌ Inyección SQL
cursor.execute("SELECT * FROM tickets WHERE id_area = " + str(id_area))
cursor.execute("SELECT * FROM tickets WHERE id_area = %s" % id_area)
```

El segundo caso es especialmente peligroso: **parece** parametrizado y no lo
está. El operador `%` interpola en Python antes de que el motor vea la
consulta.

### 5.3 Datos que salen del sistema

- Los datos personales se anonimizan **antes** de enviarse a cualquier
  servicio externo. Los correos y nombres de solicitante se reemplazan por
  identificadores opacos.
- No se envían datos reales de la compañía a herramientas externas.
- El texto proveniente del usuario **nunca** se concatena directamente a un
  prompt sin delimitación explícita ni instrucción de tratarlo como dato.
- La salida de un modelo **nunca** se escribe a base de datos ni se
  interpola en una consulta sin validarse contra un catálogo cerrado de
  valores permitidos.

### 5.4 Revisión de código generado por IA

Todo código generado por un asistente se revisa buscando específicamente:

- [ ] Credenciales embebidas
- [ ] Concatenación de cadenas en consultas SQL
- [ ] Llamadas de red sin `timeout`
- [ ] Respuestas HTTP usadas sin verificar el código de estado
- [ ] Divisiones sin verificar denominador cero
- [ ] Transacciones sin `rollback` en la ruta de error
- [ ] Recursos abiertos sin cierre garantizado
- [ ] Consultas dentro de bucles (N+1)
- [ ] Validaciones de entrada ausentes
- [ ] Dependencias añadidas sin justificación

`ruff` y `bandit` corren en CI. No sustituyen la revisión humana: la enfocan.

---

## 6. Pruebas

- Toda función pública tiene al menos una prueba de camino normal y una de
  caso de borde.
- Las pruebas no dependen de red ni de credenciales. Los servicios externos
  se sustituyen por el adaptador `falso`.
- Los nombres de prueba describen el comportamiento, no la implementación:
  `test_no_pierde_tickets_creados_el_primer_dia_del_periodo`.

### Corrección de defectos: rojo antes que verde

Al corregir un defecto, la prueba que lo demuestra se escribe **primero**,
se verifica que **falla**, y se registra en un commit separado del arreglo:

```
test(legacy): S1 — prueba que demuestra la pérdida de tickets en los extremos
fix(legacy): S1 — el filtro excluía los extremos que el contrato incluye
```

Sin la prueba en rojo previa no hay evidencia de que se entendió la causa;
solo de que el síntoma dejó de verse.

---

## 7. Observabilidad

Registro estructurado (JSON), nunca `print`. Cada evento lleva `id_traza`
propagado extremo a extremo.

Toda llamada a un proveedor externo registra: `latencia_ms`,
`tokens_entrada`, `tokens_salida`, `costo_estimado`, `proveedor`, `modelo`,
`resultado` (`exito` / `degradado` / `error`).

Métricas agregadas expuestas: latencia p50/p95/p99, tasa de error, tasa de
degradación, tasa de abstención, tokens y costo acumulado.

**Los registros no contienen datos personales ni contenido íntegro de
tickets.** Identificadores, no contenido.

---

## 8. Recuperación aumentada (RAG) y abstención

- Toda respuesta generada a partir de documentos **cita documento y
  sección**. Una respuesta sin cita no se emite.
- **Si la evidencia recuperada no supera el umbral de similitud, el sistema
  declara que no tiene evidencia.** No responde con conocimiento general del
  modelo.
- La abstención se verifica con pruebas dedicadas sobre preguntas cuyo tema
  no existe en el corpus.
- Si la respuesta generada no contiene una cita verificable contra los
  fragmentos recuperados, se descarta y se abstiene.

Inventar una respuesta plausible es peor que no responder: el usuario no
tiene forma de distinguirla de una correcta.

---

## 9. Estilo

- Python 3.11+, tipado en firmas públicas.
- Formato y análisis: `ruff`. Longitud máxima de línea: 100.
- Nombres del dominio en español; términos técnicos establecidos en inglés.
- Docstrings en funciones públicas: qué hace, qué recibe, qué devuelve, qué
  hace ante entrada inválida.
- Sin números mágicos: constantes con nombre.
- Sin argumentos mutables por defecto (`def f(x, acc={})`). Se evalúan una
  sola vez al definir la función y el estado persiste entre llamadas.

---

## 10. Commits

```
tipo(alcance): descripción en imperativo

Cuerpo opcional explicando el porqué.
```

Tipos: `feat` `fix` `test` `docs` `refactor` `chore` `ci`

- Commits atómicos: un cambio con un propósito.
- El mensaje explica **por qué**, no qué (el diff ya dice qué).
- El historial no se reescribe: sin `--amend`, `rebase -i` ni
  `push --force` sobre trabajo compartido.
- `main` permanece estable. El trabajo ocurre en ramas.

---

## 11. Dependencias

Cada dependencia se registra en [`docs/decisiones.md`](docs/decisiones.md)
con: qué problema resuelve, qué alternativas se consideraron, por qué esta,
y qué costo se acepta al adoptarla.

Antes de agregar una: ¿la biblioteca estándar resuelve esto en menos de
treinta líneas comprensibles? Si sí, se escribe.

---

## 12. Documentación de decisiones

Toda decisión de arquitectura relevante se registra como ADR en
`docs/adr/` con esta estructura:

```markdown
# ADR-00N · Título

## Contexto
## Alternativas consideradas
| Opción | A favor | En contra |
## Decisión
## Consecuencias negativas aceptadas
## Bajo qué condición se revisaría
```

Las dos últimas secciones no son opcionales. Una decisión documentada sin
costo asumido es una justificación, no una decisión.

---

## 13. Definición de terminado

Una unidad de trabajo está terminada cuando:

- [ ] Funciona en el caso normal **y** en los casos de borde definidos
- [ ] Tiene pruebas que corren sin red ni credenciales
- [ ] Los errores están manejados y no exponen trazas al usuario
- [ ] No introduce secretos ni consultas concatenadas
- [ ] Registra latencia y costo si llama a un servicio externo
- [ ] Está documentada donde corresponde
- [ ] Quien la integra puede explicarla línea por línea
- [ ] Lo que quedó fuera está declarado explícitamente

**Lo último importa tanto como el resto.** Un límite declarado es
información útil para quien mantiene el sistema. Un límite oculto es una
falla esperando ocurrir en producción.

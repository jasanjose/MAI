# Integración continua: evidencia y post mortem

**Flujo:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) · dos
trabajos, sobre Python 3.11 —el mínimo declarado en `pyproject.toml`—.

| Trabajo | Qué corre |
|---|---|
| `calidad` | `ruff check .` · `bandit -r src/ -q` · `pytest` |
| `secretos` | credenciales en archivos versionados · credenciales **en el historial** (`fetch-depth: 0`) · rutas privadas versionadas |

**El disparador no filtra por rama, y es deliberado.** El trabajo que debe
fallar ocurre en ramas de etapa, no en `main`.

---

## Historial completo: 51 ejecuciones

```
#1 – #7     verde
#8          ROJO deliberado      rama evidencia-ci-rojo-pruebas
#9 – #11    verde
#12 – #48   ROJO no intencionado 37 ejecuciones consecutivas
#49 – #51   verde                tras la corrección
```

---

## 1 · Ejecución exitosa

**`CI #1`** · rama `etapa1-fundamentos` · commit `b10ceb2` · **17 s** · verde.
Primera ejecución del flujo, a la primera.

**`CI #51`** · rama `main` · **21 s** · verde. El estado actual: los dos
trabajos pasan, incluida la auditoría del historial completo.

## 2 · Ejecución fallida, provocada a propósito

**`CI #8`** · rama `evidencia-ci-rojo-pruebas` · commit `bb7dcb9`
`test(legacy): S3 — prueba que demuestra el subconteo de reaperturas`

Es el commit con la prueba del defecto S3 **antes** de su arreglo.

```
✓ ruff check .        All checks passed!
✓ bandit -r src/ -q   (sin hallazgos)
X pytest              4 failed, 141 passed
```

**Falla en el paso de las pruebas, no antes**, y eso es lo que la hace útil:
el análisis estático pasa y lo que se rompe es la prueba que demuestra el
defecto. Se eligió este commit tras comprobar los dos candidatos — en
`8c7135d`, la prueba roja de S1, la ejecución muere en `ruff` porque el
defecto S2 sigue presente, y nunca llega a `pytest`.

## 3 · Ejecución fallida real, que nadie provocó

**`CI #12` a `CI #48` · 37 ejecuciones consecutivas en rojo**, incluida la de
`main`. El trabajo de calidad pasaba siempre; el de secretos no:

```
X Auditoria de secretos y frontera de git
    Credenciales en archivos versionados:
    tests/test_llm_compatible.py:38
```

En esa línea, el parámetro `api_key` recibía directamente un literal
entrecomillado de quince caracteres —un relleno de prueba, sin ningún valor—.
Lo introdujo `CI #12`, el commit que añadió las pruebas del adaptador de
proveedores. El patrón de credenciales coincide con esa forma, **y hace
bien**: ninguna herramienta puede distinguir un relleno de prueba de una
credencial real.

> **Nótese que esta página no reproduce la línea.** La primera versión de este
> documento la citaba textualmente, y **el post mortem que explica el falso
> positivo disparó el mismo falso positivo** — `CI #52`, rojo, señalando este
> archivo.
>
> No es una anécdota: es un costo operativo real de cualquier detector de
> secretos. Documentar un incidente exige escribir la forma que lo causó, y
> escribirla vuelve a activar la alarma. Quien mantenga esto tiene que
> saberlo, porque la salida cómoda —excluir `docs/` del análisis— dejaría sin
> vigilar justo los archivos donde alguien pega una clave «solo para el
> ejemplo».

### Por qué no se corrigió relajando el detector

Añadir una excepción por archivo, o acortar el patrón, habría puesto la
ejecución en verde en un minuto. También le habría quitado al detector justo
lo que lo hace útil, y **la próxima credencial de verdad habría pasado por el
mismo hueco**.

Lo que se cambió es no escribir la forma que dispara la alarma: el valor pasó
a una constante con nombre. El detector sigue igual de estricto y el código
quedó mejor.

### Por qué tardó 37 ejecuciones en detectarse

Dos fallos que se taparon entre sí:

**Se dejó de correr la verificación completa.** La auditoría se ejecutó al
principio del proyecto, cuando ese archivo aún no existía, y después solo se
revisaban archivos sueltos antes de cada commit. Se daba por bueno un
resultado viejo.

**No se estaba leyendo la señal que lo delataba.** La cuenta del CLI de
GitHub configurada en la máquina no tenía acceso al repositorio privado
—devolvía 404— así que las ejecuciones no se consultaban. Se supo al obtener
acceso, y entonces las 37 aparecieron de golpe.

### Qué deja este incidente

Es la mejor evidencia de que el flujo sirve, mejor que el rojo provocado:
**atrapó algo que la verificación manual había dejado de mirar.** El trabajo
de secretos existe precisamente para el momento en que alguien deja de
revisar, que es siempre.

Y deja dos reglas de proceso:

1. **La verificación completa se corre antes de cada envío, no una vez.** Un
   resultado de hace tres días no dice nada del estado actual.
2. **Una señal que no se puede leer no es una señal.** El acceso a las
   ejecuciones es parte del flujo, no un extra: sin él, el pipeline estuvo
   avisando durante horas sin que nadie lo oyera.

---

## Verificación local reproducible

Los dos estados se reproducen con `git switch --detach <commit>` y los tres
comandos del flujo:

| Estado | Commit | Resultado |
|---|---|---|
| Rojo | `bb7dcb9` | `4 failed, 141 passed` |
| Verde | punta de `main` | `501 passed` · ruff y bandit limpios |

Y la auditoría de secretos, con el patrón exacto del flujo:

```
$ git ls-files -z | xargs -0 -r grep -nEIf patrones.txt   → (vacío)
$ git log -p --all | grep -cE 'sk-[A-Za-z0-9_-]{16,}'     → 0
$ git ls-files | grep -E '^INSUMOS/|^ai-docs/|\.env$'     → (vacío)
```

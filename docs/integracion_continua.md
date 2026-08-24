# Integración continua: ejecución exitosa y ejecución fallida

**Flujo:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) · dos
trabajos, sobre Python 3.11 —el mínimo declarado en `pyproject.toml`—.

| Trabajo | Qué corre |
|---|---|
| `calidad` | `ruff check .` · `bandit -r src/ -q` · `pytest` |
| `secretos` | credenciales en archivos versionados · credenciales **en el historial** (`fetch-depth: 0`) · rutas privadas versionadas |

**El disparador no filtra por rama, y es deliberado.** El trabajo que debe
fallar ocurre en ramas de etapa, no en `main`. Un vigilante que solo escucha
`main` no registra nada de lo que pasa donde de verdad se trabaja.

---

## Ejecución fallida

**Rama:** `evidencia-ci-rojo-pruebas` → commit `bb7dcb9`
`test(legacy): S3 — prueba que demuestra el subconteo de reaperturas`

Es el commit con la prueba del defecto S3 **antes** de su arreglo. La rama
existe para que ese estado, que forma parte del historial, sea visible a
integración continua.

```
$ ruff check .
All checks passed!

$ bandit -r src/ -q
(sin hallazgos)

$ pytest
FAILED tests/test_legacy.py::test_cuenta_el_ticket_reabierto_en_mayuscula
FAILED tests/test_legacy.py::test_cuenta_el_ticket_reabierto_capitalizado
FAILED tests/test_legacy.py::test_cuenta_el_ticket_reabierto_con_espacios_sobrantes
FAILED tests/test_legacy.py::test_la_tasa_de_reapertura_refleja_el_conteo_corregido
4 failed, 141 passed
```

**Falla en el paso de las pruebas, no antes.** Eso importa: el análisis
estático pasa y lo que se rompe es la prueba que demuestra el defecto. Una
ejecución que muriera en `ruff` sería roja igual, pero no demostraría que las
pruebas atrapan defectos de lógica.

Se eligió este commit tras comprobar los dos candidatos. En `8c7135d` —la
prueba roja de S1— la ejecución se cae en `ruff`, porque el defecto S2 sigue
presente y lo marca como `B006`, y nunca llega a `pytest`.

## Ejecución exitosa

**Rama:** `etapa3-complejidad` → punta actual

```
$ ruff check .
All checks passed!

$ bandit -r src/ -q
(sin hallazgos)

$ pytest
470 passed
```

Y el trabajo de secretos, con los mismos comandos que corre el flujo:

```
$ git ls-files | xargs grep -nEIf patrones.txt      → (vacío)
$ git log -p --all | grep -nE 'sk-[A-Za-z0-9_-]{16,}' → (vacío)
$ git ls-files | grep -E '^INSUMOS/|^ai-docs/|\.env$' → (vacío)
```

---

## Qué está verificado y qué no

**Verificado:** que el flujo corre y termina en verde. La primera ejecución
—`CI #1` sobre el commit `b10ceb2`— pasó en **17 segundos**, y se comprobó en
la interfaz de Actions.

**Verificado localmente, comando por comando:** los dos estados de arriba.
Las salidas son reales, reproducibles con `git switch --detach <commit>` y
las tres órdenes del flujo.

**No capturado:** las pantallas de Actions de la ejecución fallida y de las
posteriores. La cuenta de `gh` de la máquina de desarrollo no tiene acceso al
repositorio privado —`gh run list` devuelve 404— y no se resolvió antes de la
entrega. **Se declara en vez de omitirse:** la evidencia que aquí se presenta
es la reproducción local de los mismos comandos que ejecuta el flujo, no una
captura de la ejecución remota.

---

## Una lección de proceso que costó una corrección

Se dio por hecho que empujar siete commits produciría siete ejecuciones.
**Es falso:** GitHub Actions crea **una ejecución por envío**, sobre el commit
de punta. Los siete viajaron juntos, la punta estaba en verde, y los tres
commits rojos del legacy **no dispararon nada**.

La evidencia de ejecución fallida no se generó sola, como se esperaba. Se
corrigió empujando una rama que apunta al commit rojo, y desde entonces los
commits se empujan **de uno en uno** para que cada uno tenga su ejecución.

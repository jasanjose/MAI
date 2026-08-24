# Costo y latencia: medido, no estimado

**Fecha de la medición:** 24 de agosto de 2026.
**Qué se midió:** la tarea de clasificación de MAI contra proveedores reales,
usando el `Clasificador` del dominio y `AdaptadorCompatible` — el mismo código
que correría en producción, no una réplica escrita para el banco.

Hasta esta medición el README declaraba que **ningún proveedor real se había
ejercitado** y que el costo en dinero no se estimaba. Este documento cierra las
dos cosas para la tarea de clasificación. Lo que sigue sin medirse está
declarado al final.

---

## 1 · Resultado

Sobre los **29 casos de clasificación** de
[`conjunto_referencia.csv`](conjunto_referencia.csv), etiquetados a mano. Una
pasada por caso.

| Modelo | Exactitud | p50 | p95 | USD/mes | USD/1k solicitudes |
|---|---:|---:|---:|---:|---:|
| **DeepSeek Flash** | **96,5 %** (28/29) | 516 ms | 733 ms | **5,20** | **0,0578** |
| Qwen Flash | 93,1 % (27/29) | **297 ms** | **438 ms** | 7,59 | 0,0844 |

**Recomendación: DeepSeek Flash.** Es a la vez el más exacto y el más barato.
Qwen Flash es 1,7× más rápido, pero acierta menos y cuesta un 46 % más, porque
su token de salida vale casi cuatro veces lo que el del otro.

Los dos entran holgados bajo el umbral de p95 ≤ 5 s que
[`metricas.md`](metricas.md) §3 fijó **antes** de construir. Con ese margen, la
latencia deja de ser el criterio de elección y el costo pasa a serlo.

### Cómo se calculó el costo

Con los **tokens medidos**, no con los supuestos:

```
DeepSeek Flash:  258 tokens de entrada · 15,8 de salida   por clasificación
Qwen Flash:      250 tokens de entrada · 14,6 de salida
base:            3.000 clasificaciones/día × 30 días = 90.000 llamadas/mes  (R-01)
```

Los 250 tokens de entrada **confirman el supuesto** que
[`arquitectura.md`](arquitectura.md) §7 había declarado sin medir. Los de salida
resultaron menores que los 20 asumidos, así que aquella proyección era
conservadora, no optimista.

Precios por millón de tokens tomados de la consola de cada proveedor el día de
la medición. **No se ponen de memoria y no se copian de un blog:** al
contrastar, dos publicaciones daban cifras del doble y del triple de las reales.

---

## 2 · Dos cosas que solo aparecen midiendo

### La generación siguiente no compra nada aquí

Se midió también la generación posterior de uno de los dos modelos: **acierta
exactamente lo mismo**, 27 de 29, con el mismo consumo de tokens. Clasificar en
un catálogo cerrado de 12 valores no es un problema que un modelo más nuevo
resuelva mejor — y sí es uno que un modelo más caro encarece.

El criterio que se deriva: **el más barato que resuelve, gana.** Subir de modelo
se justifica cuando el error deja de ser barato, que es el mismo umbral que
[`metricas.md`](metricas.md) §2 usa para no exigir 0,95 de precisión.

### El razonamiento hay que apagarlo, y verificarlo por efecto

Los modelos capaces de razonar antes de responder lo hacen por defecto, y para
elegir de una lista cerrada **eso no mejora la precisión**: solo añade latencia
y tokens de salida, que son los caros.

Cada proveedor nombra ese ajuste a su manera y **el nombre que no le corresponde
lo ignora sin avisar**: la petición responde bien, tarde y cara, sin ninguna
señal de error. MAI lo resuelve en
[`adaptadores/llm/perfiles.py`](../src/mai/adaptadores/llm/perfiles.py), donde
cada proveedor declara el suyo, en vez de dejarlo a quien configura el entorno.

Las corridas de arriba reportan **cero tokens y cero caracteres de
razonamiento**, comprobado sobre la respuesta recibida y no sobre el campo
enviado. La distinción importa: verificar que la petición lleva la clave
correcta da verde con la versión rota, porque el problema no es enviarla — es
que el proveedor no la mire.

---

## 3 · Qué no se midió

- **La tarea de RAG.** Solo se midió clasificación. La proyección de la consulta
  de políticas sigue siendo la de `arquitectura.md` §7, con sus supuestos
  declarados.
- **Una sola pasada por caso.** Con 29 casos y N=1, una diferencia de un acierto
  —los 3,4 puntos entre los dos modelos— está dentro de lo que puede moverse
  entre corridas. La conclusión de costo es firme; la de exactitud, indicativa.
- **El presupuesto máximo y su alerta** siguen sin construirse. Lo que este
  documento aporta es la cifra sobre la que fijarlo.
- **Descuento por caché de entrada.** Los proveedores lo ofrecen y aquí no se
  aplicó; con un prompt de sistema idéntico entre llamadas, el costo real sería
  menor que el de esta tabla.

---

## 4 · Cómo se reproduce

```bash
RUTA_CLASIFICACION=<proveedor> python scripts/evaluar.py
```

El perfil del proveedor —incluido el apagado del razonamiento— lo aplica
`perfiles.py`; no hay nada que recordar al configurar. Cambiar de modelo es
cambiar una variable de entorno, que es el criterio de aceptación de
`CLAUDE.md` §3.

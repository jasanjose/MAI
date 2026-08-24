# Comparación: modelo clásico frente a modelo de lenguaje

> Reproducible con `python scripts/entrenar_clasico.py`. No corre en
> integración continua: necesita el histórico, que no se versiona.

---

## 1 · El hallazgo que condiciona todo lo demás

La medición habitual —barajar las 2.000 filas, separar el 20 %— da esto:

```
partición por fila:   99.2 %   97.9 %   99.7 %      (tres semillas)
```

**Ese número es falso**, y la razón está en los datos:

```
2.000 filas · 50 asuntos distintos · cada texto se repite ~38 veces
```

Al barajar por filas, el mismo asunto cae en entrenamiento y en prueba. El
modelo no generaliza: **busca en una tabla que ya vio**. Y como cada asunto
tiene exactamente una categoría —se verificó: cero asuntos ambiguos—, la
búsqueda acierta siempre.

Partiendo **por asunto**, de modo que la prueba traiga textos nunca vistos:

```
partición por asunto:  9.4 %   22.7 %   6.4 %       (mismas semillas)
línea base:           15.7 %                        (predecir siempre la más frecuente)
```

**Dos de las tres quedan por debajo de la línea base.** Sin memorizar, el
modelo es peor que ignorar el texto y responder siempre «Software».

### Qué significa, dicho con precisión

No significa que Naive Bayes sea malo, ni que el enfoque clásico no sirva.
Significa que **este conjunto de datos no permite estimar cuánto generalizaría
un clasificador**. Cincuenta textos distintos repartidos en doce categorías no
son un conjunto de entrenamiento: son un diccionario.

Es una propiedad de los datos sintéticos entregados, no del problema real.

---

## 2 · Matriz de confusión

Se presenta la de la partición por fila —la de asunto deja categorías sin un
solo caso de prueba— **con la advertencia de que está inflada**.

```
               Acce  Capa  Comp  Hard  Inci  Info  Nómi  Otro   Red  Soft  Vaca  Viát
  Accesos         63     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·
  Capacitación     ·    10     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·
  Compras          ·     ·    25     ·     ·     ·     ·     ·     ·     ·     ·     ·
  Hardware         ·     ·     ·    55     ·     ·     ·     ·     ·     ·     ·     ·
  Incidentes       ·     ·     ·     ·    26     ·     ·     ·     ·     ·     ·     ·
  Informes         ·     ·     ·     ·     ·    20     ·     ·     ·     ·     ·     ·
  Nómina           ·     ·     ·     ·     ·     ·    21     ·     ·     ·     ·     ·
  Otros            1     ·     ·     ·     ·     ·     ·    25     2     ·     ·     ·
  Red              ·     ·     ·     ·     ·     ·     ·     ·    32     ·     ·     ·
  Software         ·     ·     ·     ·     ·     ·     ·     ·     ·    57     ·     ·
  Vacaciones       ·     ·     ·     ·     ·     ·     ·     ·     ·     ·    27     ·
  Viáticos         ·     ·     ·     ·     ·     ·     ·     ·     ·     ·     ·    23
```

**Una matriz casi perfectamente diagonal es, ella misma, la evidencia.** Un
clasificador de texto real confunde categorías vecinas —Software con
Incidentes, Hardware con Red— porque el lenguaje se solapa. Que aquí no pase
confirma que no está clasificando: está recordando.

Los tres únicos errores son instructivos: los tres están en **«Otros»**, la
categoría que por definición no tiene vocabulario propio. Dos se van a «Red» y
uno a «Accesos». Es el único sitio donde el modelo tuvo que decidir de verdad.

---

## 3 · La comparación, con lo que se puede y no se puede afirmar

| | Clásico (Naive Bayes) | Modelo de lenguaje |
|---|---|---|
| **Precisión medida aquí** | 99 % con fuga · **6–23 % sin ella** | **No medida**: no hay credencial |
| **Costo por 1.000 solicitudes** | ~0 variable. Costo fijo de entrenar | ~270.000 tokens de entrada |
| **Latencia** | microsegundos, en proceso | cientos de ms a segundos, por red |
| **Determinismo** | total: misma entrada, misma salida | alto con temperatura 0, no garantizado |
| **Categoría nueva** | reentrenar | una línea en el prompt |
| **Explicabilidad** | qué términos pesaron, término a término | ninguna |
| **Dependencias en ejecución** | ninguna | red, credencial, disponibilidad de un tercero |
| **Mantenimiento** | reentrenar cuando cambie el catálogo | vigilar cambios de modelo del proveedor |

### Lo que NO se puede afirmar, y por qué

**No se puede afirmar que el clásico gane, ni que pierda.** Falta:

1. **La medición del modelo de lenguaje.** Sin credencial no se ejecutó ni una
   clasificación real. Está construido y probado contra transporte simulado.
2. **Un conjunto de datos que permita estimar generalización.** El entregado
   no lo permite, y eso limita a ambos: sobre 50 textos memorizables, el
   modelo de lenguaje también acertaría casi todo.
3. **El costo real por token.** Se mide el consumo, no se estima el precio
   ([`arquitectura.md`](arquitectura.md) §7).

**Poner un número inventado en cualquiera de las tres casillas haría la tabla
más completa y menos verdadera.**

---

## 4 · Recomendación

**Se mantiene la decisión de [`decision_requerimientos.md`](decision_requerimientos.md):
combinación, con el clasificador clásico como motor y el modelo de lenguaje en
la cola de casos dudosos.** Pero el argumento cambia de sitio.

**No se sostiene en la precisión medida** —esa medición no existe— sino en las
otras seis filas de la tabla, que no dependen del conjunto de datos: costo
variable cero contra 270.000 tokens por mil solicitudes, microsegundos contra
segundos, determinismo, y cero dependencias externas en el camino crítico de
un proceso que corre 3.000 veces al día.

**Y lo que este ejercicio añade a la decisión es una condición de entrada que
antes no estaba:**

> Antes de construir el clasificador clásico en producción hay que verificar
> que el histórico **real** tenga variedad de texto. Si se parece al
> entregado —unas decenas de plantillas repetidas—, entonces no hace falta
> aprendizaje automático en absoluto: una tabla de correspondencia entre
> plantilla y categoría resuelve el 100 % con cero costo, cero latencia y
> explicabilidad total.

Ese sería el mejor desenlace posible y ninguna de las dos tecnologías lo
gana: lo gana el `SELECT`.

---

## 5 · Cómo se decidiría con datos de verdad

1. **Medir la variedad del histórico real.** Si los textos distintos son pocos
   y estables, tabla de correspondencia y se acabó.
2. **Si hay variedad, particionar por texto y no por fila.** Es la lección que
   este ejercicio deja, y aplica a cualquier conjunto con registros
   duplicados.
3. **Medir el modelo de lenguaje sobre el mismo conjunto de prueba**, con el
   conjunto de referencia de 58 casos como control.
4. **Comparar precisión contra costo por mil solicitudes**, no en abstracto.
   Con error barato —R-01: un minuto de un analista— cinco puntos de precisión
   rara vez justifican multiplicar el costo por veinte.

---

## 6 · Sobre la implementación

El clasificador está escrito a mano, sin `scikit-learn`. El estándar del
proyecto pregunta si la biblioteca estándar resuelve el problema en menos de
treinta líneas comprensibles, y aquí sí: el tokenizador ya existía —se
comparte con el componente de recuperación— y Naive Bayes multinomial son
unas treinta líneas de aritmética explicable en voz alta.

**Lo que se pierde y se acepta:** validación cruzada, búsqueda de
hiperparámetros y una docena de modelos alternativos listos para comparar. Con
un conjunto de datos que no permite estimar generalización, ninguna de las
tres habría cambiado la conclusión.

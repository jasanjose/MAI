# Guía: revisar código generado por IA

> Para el equipo de Aplicaciones. Breve a propósito: una guía que no se lee
> completa no cambia nada.
>
> **Todas las reglas salen de algo que pasó en este proyecto.** Ninguna es
> una precaución teórica; cada una tiene su incidente al lado, con el número
> que lo hizo visible. Se puede verificar en el historial.

---

## El patrón que hay que tener en la cabeza

Un asistente escribe **código que funciona en el caso que imaginó**, y
**afirma con seguridad cosas que no midió**.

Las dos mitades importan. La primera es la conocida y se atrapa con pruebas.
La segunda es la peligrosa, porque llega envuelta en explicaciones
convincentes: comentarios que justifican una protección que no protege,
docstrings que describen una garantía que el código no da.

En este proyecto, de seis correcciones sustanciales, **dos fueron pruebas que
afirmaban demostrar una condición de carrera y no demostraban nada**. El
código estaba bien; la afirmación sobre el código estaba mal.

---

## Qué se puede generar sin ceremonia

- Estructura de paquetes, configuración de herramientas, andamiaje.
- Esqueletos de pruebas y casos de borde: un asistente enumera casos que a
  una persona se le pasan.
- Adaptadores contra protocolos conocidos y bien documentados.
- Traducciones mecánicas: de un esquema a un modelo, de una tabla a un tipo.
- Documentación que se contrasta contra el código en la misma revisión.

## Qué se revisa siempre, línea por línea

Diez cosas. Es la lista de `CLAUDE.md` §5.4 con lo que este proyecto añadió.

1. **Credenciales embebidas.** Y en los mensajes de error: varios proveedores
   devuelven la clave dentro del cuerpo de un 401, y copiar ese cuerpo a una
   excepción la filtra al registro.
2. **Concatenación en consultas SQL** — incluido el operador `%`, que
   *parece* parametrización y no lo es.
3. **Llamadas de red sin `timeout`.** `requests` no trae uno por defecto.
4. **Respuestas HTTP usadas sin verificar el código de estado.**
5. **Divisiones sin comprobar el denominador.**
6. **Transacciones sin `rollback`** y recursos sin cierre garantizado.
7. **Consultas dentro de bucles.**
8. **Validaciones de entrada ausentes**, y **cotas de tamaño**: cualquier
   campo de texto sin cota es un vector de denegación de servicio.
9. **Dependencias añadidas sin justificación.**
10. **Comparaciones de texto contra literales.** Añadida por incidente
    propio: las reglas comparaban contra `"nómina"` acentuada y un ticket que
    decía `nomina` recibía la categoría equivocada. Con 300 pruebas en verde.

## Qué nunca se acepta sin prueba

- **Un arreglo sin su prueba en rojo previa, en un commit separado.** Sin
  ella hay evidencia de que el síntoma desapareció, no de que se entendió la
  causa.
- **Una prueba de concurrencia sin haber verificado que falla con la
  implementación rota.** Ver más abajo.
- **Una afirmación numérica sin la ejecución que la produjo.** «Mejora el
  rendimiento», «cubre todos los casos», «es más rápido»: o hay una medición
  o se borra la frase.
- **Salida de un modelo escrita a persistencia** sin validar contra un
  catálogo cerrado.
- **Texto de un usuario concatenado a un prompt** sin delimitación y sin
  instrucción de tratarlo como dato.

---

## Cuatro prácticas, en orden de cuánto encontraron

### 1 · Ejecutar la aplicación, no solo la suite

Encontró **tres defectos que 470 pruebas en verde no vieron**. El de las
tildes salió a la primera petición real; los otros dos eran huecos de
diagnóstico en la sonda de salud.

> Una suite verde no dice que el código funcione con datos reales. Dice que
> funciona con los datos que se le ocurrieron a quien la escribió — y quien
> la escribió fue el mismo que escribió el código.

### 2 · Romper la implementación a propósito

Antes de creer que una prueba protege algo, sustituya el código por una
versión deliberadamente defectuosa y **compruebe que la prueba se pone roja**.

Así se descubrió que dos pruebas de concurrencia de este proyecto no tenían
dientes: con el cerrojo quitado, **seguían pasando**. Bajo el GIL de CPython
la ventana de la carrera es demasiado estrecha, y el cliente de pruebas de
FastAPI encima serializa las peticiones.

Las dos se conservaron, con las docstrings reescritas para decir lo que
realmente son: red de regresión, no demostración. Una prueba que no puede
demostrar lo que afirma sigue sirviendo; una que *dice* demostrarlo, engaña.

### 3 · Medir contra los datos reales, no contra ejemplos

Cada corrección del módulo heredado se cuantificó sobre los 2.000 registros
entregados: S1 recupera 16 tickets perdidos, S3 lleva la tasa de reapertura
de 8,25 % a 26,4 %. Un ejemplo inventado habría confirmado el arreglo sin
decir nada sobre su importancia.

Y sirve en la otra dirección: la fragmentación del corpus se validó por
cobertura de vocabulario —717 de 717 palabras— antes de confiar en ella.

### 4 · Dejar que la herramienta enfoque, no que decida

`ruff` con las reglas de seguridad y `bandit` corren en cada envío. En este
proyecto detectaron **uno de siete hallazgos de seguridad**: el argumento
mutable por defecto, que es un defecto de *forma*.

No detectaron —ni podían— la inyección de registros por cabecera, la falta de
validación de la salida del modelo, ni que un dato personal viajara a un
tercero. Esos exigen saber qué hace el sistema y con qué datos.

> El análisis estático dice dónde mirar. No dice si lo que hay ahí está bien.

---

## Cómo pedir el trabajo

**Pida alternativas antes que código.** «Dame dos formas de hacerlo con el
costo de cada una» produce una decisión que se puede defender; «hazlo»
produce código que hay que ingeniería-inversa después.

**Pida el rojo antes que el verde.** Al corregir un defecto: primero la
prueba que falla, en su propio commit.

**Pida que le señale lo que no cubrió.** Un asistente enumera con gusto lo
que hizo. Hay que preguntar explícitamente qué caso de borde quedó fuera.

**Desconfíe de las afirmaciones seguras sobre herramientas.** En este
proyecto se afirmó que empujar siete commits produciría siete ejecuciones de
integración continua. Se crea **una por envío**, sobre el commit de punta, y
la evidencia que se buscaba no se generó.

---

## Qué va al repositorio y qué no

El historial de un repositorio es un documento técnico que otra persona va a
leer dentro de dos años.

**Va al commit:** qué cambió y por qué; la causa raíz cuando es un arreglo;
la alternativa descartada y el costo aceptado; el efecto medido con números
reales; referencias a documentos versionados del propio proyecto.

**No va al commit:** el contexto de por qué se está haciendo el trabajo, las
notas de proceso, el cálculo de plazos, lo que se le va a explicar a alguien.

**Prueba rápida:** si el mensaje seguiría teniendo sentido para quien mantenga
esto dentro de dos años, va. Si solo tiene sentido para quien lo está mirando
esta semana, va a las notas.

---

## Lo que hay que declarar, siempre

Qué se generó, qué se corrigió y por qué, y cómo se verificó. Llevado **en
vivo**, no reconstruido al final: reconstruirlo de memoria produce una
declaración vaga, y la especificidad es lo único que la hace útil.

Declararlo no resta. Un equipo que sabe qué partes de su sistema salieron de
un asistente sabe dónde mirar primero cuando algo falla.

# Pantalla de solicitudes · Angular

Consume la API de MAI y muestra el listado con filtros por área, estado,
categoría y prioridad. **Es una sola pantalla**, y a propósito: el requisito
es consumir la API y filtrar; añadir enrutado, estado global o una librería de
componentes sería resolver problemas que esta pantalla no tiene.

## Cómo correrla

Hacen falta las dos partes. Primero la API, **con el origen del servidor de
desarrollo autorizado**:

```bash
# desde la raíz del repositorio
MAI_ORIGENES_PERMITIDOS=http://localhost:4200 python -m mai.api
```

Después la pantalla:

```bash
cd frontend
npm install
npm start          # http://localhost:4200
```

### Si el puerto 8000 está ocupado

Pasa, y entonces las instrucciones de arriba no llevan a ninguna parte. La API
se levanta donde haya sitio y la pantalla se entera **una sola vez**:

```bash
python -m uvicorn mai.api.main:app --port 8010     # o el que esté libre
```

```js
// en la consola del navegador. Sobrevive a la recarga.
localStorage.MAI_API = 'http://127.0.0.1:8010'; location.reload();
```

**No sirve `window.MAI_API = …; location.reload()`**: la recarga destruye la
variable antes de que la aplicación la lea, y sin recargar el cliente ya
resolvió su dirección. Es un error fácil de cometer y difícil de ver.

La dirección se resuelve en tres pasos —`window.MAI_API`, que inyecta
`index.html` al desplegar; `localStorage`, para desarrollo; y el valor por
defecto— y siempre en tiempo de ejecución, nunca al compilar: recompilar para
cambiar una URL es lo que produce «funciona en mi máquina».

**No se acepta la dirección desde la barra del navegador.** Un `?api=…` sería
más cómodo y permitiría que un enlace de un tercero apuntara la pantalla a un
servidor que no es el suyo.

## Qué hay que saber

**Sin `MAI_ORIGENES_PERMITIDOS`, el navegador bloquea las llamadas.** La API
no autoriza ningún origen cruzado por defecto, y **no acepta `*`**: un comodín
permitiría que cualquier página abierta en el navegador del usuario llamara a
la API. Si la pantalla muestra «No se pudo conectar», esa variable es lo
primero que hay que revisar.

**La marca «degradada» junto a una categoría no es decoración.** Significa que
la clasificación la puso una regla de reserva y no el modelo — porque el
proveedor no respondió, o devolvió algo fuera del catálogo. Acierta menos y
conviene revisarla. Pasando el cursor por encima se ve el motivo.

Tratar las dos igual es el error más probable al integrarse con esta API, y
por eso la pantalla las distingue.

## El sistema de diseño, y por qué es CSS y nada más

Estilo **data-dense**: filas de 36 px, tipografía de 12-14 px, cabecera fija al
desplazar, relleno de 8-12 px. La pantalla es una tabla de trabajo, no una
página de producto.

Tres reglas que se siguieron y se pueden comprobar leyendo `app.css`:

**El color nunca lleva la información solo.** Cada ficha de estado o prioridad
es punto + color + texto, y la marca de degradada añade un icono SVG. Quien no
distingue un matiz recibe lo mismo. Es la regla de accesibilidad de mayor
severidad y la más fácil de incumplir sin notarlo.

**Contraste verificado, no supuesto.** Los tres neutros van anotados con su
ratio sobre blanco en el propio archivo. El más tenue es 4,6:1 — justo sobre el
mínimo, y a propósito: es texto secundario, no decoración.

**Foco visible y movimiento opcional.** `:focus-visible` en todo lo interactivo,
y `prefers-reduced-motion` anula las transiciones.

**Sin Google Fonts.** Se usa la pila del sistema. Pedirle dos fuentes a un
tercero solo para renderizar sería incoherente con no haber traído una librería
de componentes — y esa es justamente la afirmación que esta pantalla sostiene:
`package.json` no ganó una sola dependencia.

## Estructura

```
src/app/api.ts     cliente HTTP y tipos de la API
src/app/app.ts     estado de la pantalla, con señales
src/app/app.html   plantilla
src/app/app.css    estilos
```

## Límites declarados

- **Los catálogos están escritos en el cliente.** Las ocho áreas, los cinco
  estados, las doce categorías y las cuatro prioridades se repiten aquí porque
  la API no los expone. Es deuda: si el catálogo cambia en el servidor, esta
  lista no se entera. Lo correcto sería un `GET /catalogos`.
- **No hay pruebas de la pantalla.** El andamiaje de pruebas se retiró en vez
  de dejarlo vacío fingiendo cobertura. La lógica que valía la pena probar
  —filtrar, paginar, traducir errores— está en `api.ts` y `app.ts` y es
  probable, pero no está probada.
- **No hay creación de solicitudes desde la pantalla**, solo consulta. El
  requisito pedía el listado con filtros.
- **No hay autenticación**, porque la API tampoco la tiene.
- **El motivo de una degradación solo se ve al pasar el cursor.** Es un
  `title`, y en pantalla táctil no hay cursor que pasar. La marca sí se ve
  siempre —icono, color y texto—; lo que queda oculto es el porqué. Ponerlo
  inline en cada fila cargaría la tabla, y hacerlo desplegable pedía estado
  que esta pantalla no tiene. Se declara en vez de resolverlo a medias.

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

Si la API corre en otro puerto, se cambia sin recompilar: `window.MAI_API` se
define en `src/index.html` y se resuelve en tiempo de ejecución.

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

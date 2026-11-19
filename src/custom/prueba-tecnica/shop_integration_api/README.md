# API para la tienda en línea (`shop_integration_api`)

Endpoint para que la tienda en línea consulte el catálogo de productos con sus existencias
(ejercicio 1 de la prueba técnica). Odoo 17.0.

## Tramos completados

- **A** completo.
- B y C no realizados en esta entrega (el diseño propuesto está al final).

## Cómo probarlo

```bash
./odoo test prueba-tecnica -d prueba_limpia -m shop_integration_api
```

Resultado: **8 pruebas, 0 fallos, 0 errores**; cobertura del módulo **98 %** (la única rama sin
cubrir es un error sin campo `field`, que el tramo A no produce).

Pruebas (`tests/test_products_api.py`, `HttpCase`, con un usuario vendedor autenticado):

| Prueba | Qué demuestra |
|---|---|
| `test_only_saleable_products` | Solo aparecen productos con `sale_ok` |
| `test_payload_shape` | Forma exacta de cada producto: id, código, nombre, precio, cantidad |
| `test_filter_category_includes_children` | `category_id` incluye las subcategorías |
| `test_filter_in_stock` | `in_stock=1` deja solo los productos con existencias |
| `test_filter_modified_since` | `modified_since` filtra por fecha (con y sin `Z`) |
| `test_invalid_date_returns_400` | Una fecha mala da 400 `INVALID_DATE`, **no 500** |
| `test_invalid_category_returns_400` | Una categoría mala da 400 `INVALID_PARAMETER` |
| `test_requires_login` | Sin sesión, la ruta no devuelve datos (redirige al inicio de sesión) |

Prueba manual: con una sesión iniciada en el navegador,
`http://localhost:8069/api/v1/products?in_stock=1`.

## Contrato

### `GET /api/v1/products`

Requiere una sesión de usuario interno (`auth="user"`). En el tramo B se reemplaza por una clave API.

| Parámetro | Tipo | Efecto |
|---|---|---|
| `category_id` | entero positivo | Productos de esa categoría **y de sus subcategorías** |
| `in_stock` | `1`, `true` o `yes` | Solo productos con existencias a mano mayores que cero |
| `modified_since` | fecha ISO 8601 (`2026-11-01`, `2026-11-01T10:00:00`, `…Z`, `…-04:00`) | Productos cuya variante **o** plantilla cambió desde esa fecha. Sin zona horaria se interpreta como UTC |

Siempre: solo productos vendibles (`sale_ok`), ordenados por `id`.

Respuesta 200:

```json
{
  "data": [
    {"id": 12, "default_code": "CAM-M", "name": "Camisa M", "price": 15.0,
     "qty_available": 5.0, "category": "Ropa / Camisas"}
  ]
}
```

### Errores

Formato común:

```json
{"error": {"code": "INVALID_DATE", "field": "modified_since", "message": "La fecha debe tener formato ISO 8601, por ejemplo 2026-11-01T10:00:00."}}
```

| HTTP | `error.code` | Cuándo |
|---|---|---|
| 400 | `INVALID_DATE` | `modified_since` no es una fecha ISO 8601 |
| 400 | `INVALID_PARAMETER` | `category_id` no es un entero positivo |
| 303 | — | Sin sesión: Odoo redirige al inicio de sesión (en el tramo B será 401 `UNAUTHORIZED`) |

## Decisiones

- **`type="http"` con `request.make_json_response`**, no `type="json"`: el contrato necesita
  códigos HTTP reales (400, 401, 422…); `type="json"` es JSON-RPC y responde 200 incluso con errores.
- **Se exponen variantes (`product.product`)**, no plantillas: el código interno y las
  existencias son de la variante (una camisa M y una L son productos distintos para la tienda).
- **Errores del cliente separados de los nuestros:** una excepción `ApiError` se convierte en
  la respuesta 400; un error inesperado sigue siendo un 500 y queda en el log.
- **Orden estable por `id`**, pensando en la paginación del tramo C.
- **Existencias sin una consulta por producto:** `qty_available` no se guarda en la base, pero
  Odoo lo calcula para todo el conjunto de productos de una vez al serializar (prefetch).

## Supuestos

- `category_id` incluye las subcategorías (una tienda que pide "Ropa" espera también "Ropa / Camisas").
- `qty_available` son las existencias a mano: no descuenta lo reservado para otros pedidos.
  Si la tienda necesita "lo que se puede vender ya", la alternativa es `free_qty`. Pregunta al cliente.
- `modified_since` considera los cambios de la variante **y** de la plantilla, porque el precio
  y el nombre se editan en la plantilla.
- Una fecha sin zona horaria se interpreta como UTC (así guarda Odoo las fechas).

## Limitaciones conocidas

- Sin paginación (tramo C): con un catálogo grande, la respuesta trae todos los productos.
- Sin autenticación por clave API (tramo B): hoy la tienda necesitaría una sesión de usuario.

## Tramos B y C (no realizados): diseño propuesto

- **B:** rutas con `auth="public"`; la cabecera `Authorization: Bearer <clave>` se valida con
  `res.users.apikeys._check_credentials(scope="rpc", key=…)` y `request.update_env(user=uid)`,
  así el pedido se crea con los permisos del usuario técnico de la tienda, sin `sudo()`.
  `POST /api/v1/orders` valida todas las líneas antes de crear (error 422 con
  `field: "lines[i].default_code"`) y crea una **cotización**. Modelo `shop.api.log` (endpoint,
  usuario, código HTTP, código de error, duración), escrito con un `sudo()` justificado, que nunca
  guarda la cabecera ni el cuerpo.
- **C:** paginación `limit`/`offset` con `meta.total`; `Idempotency-Key` con restricción `unique`
  y hash del cuerpo (409 si cambia); webhook al validar la entrega mediante una cola y un cron
  con reintentos (no se llama a la tienda dentro de la validación); `openapi.yaml`.

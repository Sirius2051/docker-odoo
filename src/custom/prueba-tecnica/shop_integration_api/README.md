# API para la tienda en línea (`shop_integration_api`)

API REST para que la tienda en línea consulte el catálogo con existencias y cree pedidos en
Odoo, sin tener que llamarnos para integrarse (ejercicio 1 de la prueba técnica). Odoo 17.0.
Contrato completo en [openapi.yaml](openapi.yaml).

## Tramos completados

- **A:** catálogo `GET /api/v1/products` con filtros y errores 400 (no 500).
- **B:** autenticación con clave API, `POST /api/v1/orders` con errores 422 y registro de llamadas.
- **C:** paginación, `Idempotency-Key`, existencias sin una consulta por producto (probado),
  webhook de entrega con reintentos y `openapi.yaml`.

## Cómo probarlo

```bash
./odoo test prueba-tecnica -d prueba_limpia -m shop_integration_api
```

Resultado: **27 pruebas, 0 fallos, 0 errores**; cobertura del módulo **93 %**.

| Archivo | Pruebas | Qué demuestra |
|---|---|---|
| `test_products_api.py` | 11 | Solo productos vendibles; forma de la respuesta; filtros de categoría (con subcategorías), existencias y fecha; fecha o categoría mala → 400; sin sesión ni clave → 401; la clave API sola da acceso; metadatos de paginación; `limit` mayor que 200 → 400 |
| `test_orders_api.py` | 11 | Crea una **cotización** con el usuario de la clave (sin `sudo`); sin clave o clave mala → 401; producto o cliente inexistente y cantidad inválida → 422 con `field`; JSON roto → 400; las llamadas quedan registradas **sin la clave**; idempotencia: mismo cuerpo → mismo pedido, otro cuerpo → 409, el orden de los campos no importa |
| `test_stock_queries.py` | 1 | Serializar 20 productos no hace más consultas que serializar 2 (sin N+1) |
| `test_webhook.py` | 4 | Validar la entrega encola el evento **sin llamar a la tienda**; los pedidos que no vienen de la tienda no encolan; reintenta tras un fallo y luego envía; se da por vencido tras 6 intentos |

### Prueba manual (base `dev`, tramo B)

Usuario técnico *Tienda en línea* (grupo vendedor) con su clave API, un cliente con RIF
`J123456789` y un producto `API-001`:

| Llamada | Resultado |
|---|---|
| `GET /api/v1/products` con clave | 200, 36 productos, incluido `API-001` |
| `GET /api/v1/products` sin clave | 401 `UNAUTHORIZED` |
| `POST /api/v1/orders` válido | 201 → `S00025` en borrador, creado por el usuario `tienda`, 2 unidades |
| `POST` con un producto inexistente | 422 `PRODUCT_NOT_FOUND`, `field: "lines[1].default_code"` |
| `POST` con clave mala | 401 `UNAUTHORIZED` |
| `POST` con JSON roto | 400 `INVALID_JSON` |

Las seis llamadas quedaron en el registro (también las fallidas), con usuario, código y
duración; la clave no aparece en ninguna fila (búsqueda sobre todos los campos: 0 resultados).

## Configuración

1. **Usuario técnico:** crear un usuario (por ejemplo *Tienda en línea*) con el grupo
   *Ventas: Usuario: solo documentos propios*. Los pedidos se crean con sus permisos y su nombre.
2. **Clave API:** entrando como ese usuario, *Preferencias → Seguridad de la cuenta → Nueva clave
   API*. Se entrega a la tienda; se revoca desde el mismo lugar sin tocar la contraseña.
3. **Webhook:** *Ajustes → Técnico → Parámetros del sistema* → `shop_integration_api.webhook_url`
   con la URL de la tienda. Sin este parámetro no se encolan eventos.

## Contrato

### `GET /api/v1/products`

Autenticación: `Authorization: Bearer <clave>` o una sesión de usuario interno.

| Parámetro | Tipo | Efecto |
|---|---|---|
| `category_id` | entero positivo | Productos de esa categoría **y de sus subcategorías** |
| `in_stock` | `1`, `true` o `yes` | Solo productos con existencias a mano mayores que cero |
| `modified_since` | fecha ISO 8601 (`2026-11-01`, `2026-11-01T10:00:00`, `…Z`, `…-04:00`) | Productos cuya variante **o** plantilla cambió desde esa fecha. Sin zona horaria se interpreta como UTC |
| `limit` | entero de 1 a 200 (por defecto 50) | Tamaño de la página |
| `offset` | entero ≥ 0 (por defecto 0) | Desde qué posición |

Siempre: solo productos vendibles (`sale_ok`), ordenados por `id`.

Respuesta 200:

```json
{
  "data": [
    {"id": 12, "default_code": "CAM-M", "name": "Camisa M", "price": 15.0,
     "qty_available": 5.0, "category": "Ropa / Camisas"}
  ],
  "meta": {"total": 134, "limit": 50, "offset": 0, "next_offset": 50}
}
```

`next_offset` es `null` en la última página.

### `POST /api/v1/orders`

Cabeceras: `Authorization: Bearer <clave>` (obligatoria) e `Idempotency-Key` (opcional, recomendada).

```json
{"customer_vat": "J123456789", "external_reference": "WEB-1001",
 "lines": [{"default_code": "API-001", "quantity": 2}]}
```

Respuesta 201: `{"data": {"id": 42, "name": "S00042", "state": "draft"}}`.

Se validan **todas** las líneas antes de crear: si una falla, no se crea nada y el error dice cuál.

**Idempotencia:** la misma `Idempotency-Key` con el mismo cuerpo devuelve la misma respuesta
(201, el mismo pedido) sin crear otro; con un cuerpo distinto, 409. La clave es por usuario.

### Errores

```json
{"error": {"code": "PRODUCT_NOT_FOUND", "field": "lines[1].default_code", "message": "No existe un producto vendible con código 'NO-EXISTE'."}}
```

| HTTP | `error.code` | Cuándo |
|---|---|---|
| 400 | `INVALID_DATE`, `INVALID_PARAMETER`, `INVALID_JSON`, `INVALID_BODY` | Parámetro o cuerpo mal formado |
| 401 | `UNAUTHORIZED` | Sin clave, o clave inválida |
| 409 | `IDEMPOTENCY_CONFLICT` | La clave de idempotencia ya se usó con otro cuerpo |
| 409 | `IDEMPOTENCY_IN_PROGRESS` | Otra petición con la misma clave se está procesando |
| 422 | `REQUIRED_FIELD`, `CUSTOMER_NOT_FOUND`, `PRODUCT_NOT_FOUND`, `INVALID_LINE`, `INVALID_QUANTITY` | Datos bien formados pero imposibles de procesar; `field` indica cuál |
| 500 | `INTERNAL_ERROR` | Error nuestro; el detalle queda solo en el log del servidor |

### Webhook de entrega

Al validar la entrega de un pedido creado por la API, Odoo encola un evento `delivery.done`. Un
cron (cada minuto) lo envía por `POST` a la URL configurada, con la cabecera `X-Shop-Event` y un
tiempo máximo de 10 segundos. Si falla, reintenta a los 1, 5, 15, 60 y 240 minutos; después del
sexto intento queda `failed`. **La validación nunca espera a la tienda.**

```json
{"event": "delivery.done", "order_id": 42, "order_name": "S00042",
 "external_reference": "WEB-1001", "delivery": "WH/OUT/00012", "date_done": "2026-11-20 14:03:11"}
```

## Registro de llamadas

*Ventas → Configuración → API de la tienda* (gerente de ventas, solo lectura): endpoint, método,
usuario, código HTTP, código de error, duración y pedido. Se registran también las fallidas.
Nunca se guardan cabeceras ni cuerpo (la clave viaja ahí). Se borran solos a los 90 días.

## Decisiones

- **`type="http"` con `request.make_json_response`**, no `type="json"`: el contrato necesita
  códigos HTTP reales; `type="json"` es JSON-RPC y responde 200 incluso con errores.
- **Se exponen variantes (`product.product`)**, no plantillas: el código interno y las
  existencias son de la variante.
- **Claves API nativas de Odoo** (`res.users.apikeys`): se guardan cifradas y se revocan sin tocar
  la contraseña. Tras validar la clave, `request.update_env(user=uid)`: **todo corre con los
  permisos del usuario técnico**, sin `sudo()`. El pedido aparece creado por él.
- **Un solo `sudo()` por tabla técnica:** registro de llamadas, idempotencia y cola de webhooks.
  El usuario de la tienda no debe poder leerlas ni modificarlas.
- **El registro sobrevive a los errores:** la creación del pedido va dentro de un `savepoint`; si
  falla, se deshace solo lo del pedido y el registro se escribe igual.
- **Idempotencia protegida por la base de datos:** restricción `unique(key, user_id)`, y la fila de
  idempotencia se crea en el mismo `savepoint` que el pedido. Dos peticiones simultáneas con la
  misma clave: la segunda choca con la restricción, su pedido se deshace y responde 409. Un `if`
  en Python no alcanzaría (las dos leerían "no existe"). El hash del cuerpo usa `sort_keys`.
- **Existencias en lote:** `qty_available` no se guarda en la base, pero Odoo lo calcula para todo
  el conjunto de productos de una vez (prefetch). Probado contando consultas con 2 y 20 productos.
- **Webhook por cola y cron**, no una llamada dentro de la validación: si la tienda tarda o está
  caída, el almacenista valida igual, y los eventos pendientes sobreviven a un reinicio de Odoo.
  Solo encolan los pedidos marcados como creados por la API (`shop_origin`).

## Supuestos

- El pedido se crea como **cotización** (borrador), para que un humano revise precio, crédito y
  existencias antes de comprometer inventario. **Pregunta al cliente:** si la tienda ya cobró
  cuando llama a la API, conviene confirmarlo automáticamente.
- `category_id` incluye las subcategorías.
- `qty_available` son las existencias a mano: no descuenta lo reservado para otros pedidos (la
  alternativa sería `free_qty`).
- `modified_since` considera los cambios de la variante **y** de la plantilla; una fecha sin zona
  horaria es UTC.
- El índice de `lines[i]` empieza en 0.
- El RIF se compara sin distinguir mayúsculas, pero sin normalizar guiones (`J-12345678-9` y
  `J123456789` son distintos).
- La respuesta repetida por idempotencia devuelve 201, igual que la primera.

## Limitaciones conocidas

- El RIF no se normaliza (ver supuestos).
- Si toda la transacción falla por un error de base de datos, el registro de esa llamada se pierde
  con ella; registrarlo siempre requeriría un cursor separado.
- El webhook no lleva firma (HMAC) para que la tienda verifique que viene de Odoo: es la mejora
  siguiente.
- Al instalar, Odoo muestra avisos de `docutils` (`Undefined substitution referenced: "---"`):
  interpreta este README en Markdown como reStructuredText para la descripción del módulo. No
  afecta al funcionamiento.

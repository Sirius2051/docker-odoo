import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import psycopg2

from odoo import Command, http
from odoo.http import request

_logger = logging.getLogger(__name__)

TRUE_VALUES = {"1", "true", "yes"}
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class ApiError(Exception):
    def __init__(self, code, message, field=None, status=422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.status = status


class ShopApiController(http.Controller):
    def _error_response(self, status, code, message, field=None):
        error = {"code": code, "message": message}
        if field:
            error["field"] = field
        return request.make_json_response({"error": error}, status=status)

    def _authenticate_bearer(self):
        header = request.httprequest.headers.get("Authorization", "")
        scheme, _sep, key = header.partition(" ")
        if scheme.lower() != "bearer" or not key.strip():
            return None
        uid = request.env["res.users.apikeys"]._check_credentials(scope="rpc", key=key.strip())
        if uid:
            request.update_env(user=uid)
        return uid

    def _require_api_user(self):
        if self._authenticate_bearer():
            return True
        return not request.env.user._is_public()

    def _log_call(self, started, response, error_code=None, order=None):
        request.env["shop.api.log"].sudo().create({
            "endpoint": request.httprequest.path,
            "method": request.httprequest.method,
            "user_id": False if request.env.user._is_public() else request.env.user.id,
            "status_code": response.status_code,
            "error_code": error_code,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "order_id": order.id if order else False,
        })

    def _parse_datetime(self, value, field):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            raise ApiError(
                "INVALID_DATE",
                "La fecha debe tener formato ISO 8601, por ejemplo 2026-11-01T10:00:00.",
                field=field,
                status=400,
            )
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    def _parse_positive_int(self, value, field):
        if not value.isdigit() or int(value) <= 0:
            raise ApiError("INVALID_PARAMETER", "Debe ser un número entero positivo.", field=field, status=400)
        return int(value)

    def _parse_pagination(self, params):
        limit = DEFAULT_LIMIT
        if params.get("limit"):
            limit = self._parse_positive_int(params["limit"], "limit")
            if limit > MAX_LIMIT:
                raise ApiError("INVALID_PARAMETER", f"El máximo es {MAX_LIMIT}.", field="limit", status=400)
        offset = 0
        if params.get("offset"):
            if not params["offset"].isdigit():
                raise ApiError("INVALID_PARAMETER", "Debe ser un entero mayor o igual que cero.", field="offset", status=400)
            offset = int(params["offset"])
        return limit, offset

    def _products_domain(self, params):
        domain = [("sale_ok", "=", True)]
        if params.get("category_id"):
            category_id = self._parse_positive_int(params["category_id"], "category_id")
            domain.append(("categ_id", "child_of", category_id))
        if (params.get("in_stock") or "").lower() in TRUE_VALUES:
            domain.append(("qty_available", ">", 0))
        if params.get("modified_since"):
            since = self._parse_datetime(params["modified_since"], "modified_since")
            domain += ["|", ("write_date", ">=", since), ("product_tmpl_id.write_date", ">=", since)]
        return domain

    def _serialize_product(self, product):
        return {
            "id": product.id,
            "default_code": product.default_code or None,
            "name": product.name,
            "price": product.lst_price,
            "qty_available": product.qty_available,
            "category": product.categ_id.complete_name,
        }

    @http.route("/api/v1/products", type="http", auth="public", methods=["GET"])
    def list_products(self, **params):
        started = time.perf_counter()
        if not self._require_api_user():
            response = self._error_response(401, "UNAUTHORIZED", "Falta la clave API o no es válida.")
            self._log_call(started, response, "UNAUTHORIZED")
            return response
        try:
            domain = self._products_domain(params)
            limit, offset = self._parse_pagination(params)
        except ApiError as error:
            response = self._error_response(error.status, error.code, error.message, error.field)
            self._log_call(started, response, error.code)
            return response
        Product = request.env["product.product"]
        total = Product.search_count(domain)  # C
        products = Product.search(domain, order="id", limit=limit, offset=offset)
        next_offset = offset + limit if offset + limit < total else None
        response = request.make_json_response({
            "data": [self._serialize_product(p) for p in products],
            "meta": {"total": total, "limit": limit, "offset": offset, "next_offset": next_offset},
        })
        self._log_call(started, response)
        return response

    def _find_customer(self, payload):
        vat = (payload.get("customer_vat") or "").strip()
        if not vat:
            raise ApiError("REQUIRED_FIELD", "El RIF del cliente es obligatorio.", field="customer_vat")
        partner = request.env["res.partner"].search([("vat", "=ilike", vat)], limit=1)
        if not partner:
            raise ApiError("CUSTOMER_NOT_FOUND", f"No existe un cliente con RIF {vat}.", field="customer_vat")
        return partner

    def _prepare_order_lines(self, lines):
        if not isinstance(lines, list) or not lines:
            raise ApiError("REQUIRED_FIELD", "El pedido debe tener al menos una línea.", field="lines")
        codes = [line.get("default_code") for line in lines if isinstance(line, dict)]
        products = request.env["product.product"].search([("default_code", "in", codes), ("sale_ok", "=", True)])
        products_by_code = {product.default_code: product for product in products}

        commands = []
        for index, line in enumerate(lines):
            if not isinstance(line, dict):
                raise ApiError("INVALID_LINE", "Cada línea debe ser un objeto.", field=f"lines[{index}]")
            code = line.get("default_code")
            product = products_by_code.get(code)
            if not product:
                raise ApiError(
                    "PRODUCT_NOT_FOUND",
                    f"No existe un producto vendible con código {code!r}.",
                    field=f"lines[{index}].default_code",
                )
            quantity = line.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or quantity <= 0:
                raise ApiError(
                    "INVALID_QUANTITY", "La cantidad debe ser un número mayor que cero.",
                    field=f"lines[{index}].quantity",
                )
            commands.append(Command.create({"product_id": product.id, "product_uom_qty": quantity}))
        return commands

    def _create_order(self, payload):
        if not isinstance(payload, dict):
            raise ApiError("INVALID_BODY", "El cuerpo debe ser un objeto JSON.", status=400)
        partner = self._find_customer(payload)
        order_lines = self._prepare_order_lines(payload.get("lines"))
        return request.env["sale.order"].create({
            "partner_id": partner.id,
            "client_order_ref": payload.get("external_reference"),
            "order_line": order_lines,
            "shop_origin": True,
        })

    def _request_hash(self, payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _replay_or_conflict(self, key, payload):
        Idempotency = request.env["shop.api.idempotency"].sudo()
        previous = Idempotency.search([("key", "=", key), ("user_id", "=", request.env.uid)], limit=1)
        if not previous:
            return None
        if previous.request_hash != self._request_hash(payload):
            raise ApiError(
                "IDEMPOTENCY_CONFLICT",
                "Esta clave de idempotencia ya se usó con un cuerpo distinto.",
                field="Idempotency-Key",
                status=409,
            )
        return request.make_json_response(json.loads(previous.response_body), status=previous.response_status)

    @http.route("/api/v1/orders", type="http", auth="public", methods=["POST"], csrf=False)
    def create_order(self):
        started = time.perf_counter()
        if not self._authenticate_bearer():
            response = self._error_response(401, "UNAUTHORIZED", "Falta la clave API o no es válida.")
            self._log_call(started, response, "UNAUTHORIZED")
            return response

        order = None
        error_code = None
        idempotency_key = (request.httprequest.headers.get("Idempotency-Key") or "").strip()
        try:
            try:
                payload = request.get_json_data()
            except ValueError:
                raise ApiError("INVALID_JSON", "El cuerpo no es JSON válido.", status=400)

            replay = self._replay_or_conflict(idempotency_key, payload) if idempotency_key else None 
            if replay is not None:
                response = replay
            else:
                with request.env.cr.savepoint():
                    order = self._create_order(payload)
                    body = {"data": {"id": order.id, "name": order.name, "state": order.state}}
                    if idempotency_key: 
                        request.env["shop.api.idempotency"].sudo().create({
                            "key": idempotency_key,
                            "user_id": request.env.uid,
                            "request_hash": self._request_hash(payload),
                            "order_id": order.id,
                            "response_status": 201,
                            "response_body": json.dumps(body),
                        })
                response = request.make_json_response(body, status=201)
        except ApiError as error:
            error_code = error.code
            order = None
            response = self._error_response(error.status, error.code, error.message, error.field)
        except psycopg2.IntegrityError:
            error_code = "IDEMPOTENCY_IN_PROGRESS"
            order = None
            response = self._error_response(
                409, "IDEMPOTENCY_IN_PROGRESS",
                "Otra petición con la misma clave de idempotencia se está procesando.",
                field="Idempotency-Key",
            )
        except Exception:
            _logger.exception("Error inesperado creando un pedido desde la tienda")
            error_code = "INTERNAL_ERROR"
            order = None
            response = self._error_response(500, "INTERNAL_ERROR", "Error interno. Intente de nuevo más tarde.")
        self._log_call(started, response, error_code, order)
        return response
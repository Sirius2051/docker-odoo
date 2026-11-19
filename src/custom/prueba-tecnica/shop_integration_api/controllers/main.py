import logging
from datetime import datetime, timezone

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TRUE_VALUES = {"1", "true", "yes"}


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

    @http.route("/api/v1/products", type="http", auth="user", methods=["GET"])
    def list_products(self, **params):
        try:
            domain = self._products_domain(params)
        except ApiError as error:
            return self._error_response(error.status, error.code, error.message, error.field)
        products = request.env["product.product"].search(domain, order="id")
        return request.make_json_response({"data": [self._serialize_product(p) for p in products]})
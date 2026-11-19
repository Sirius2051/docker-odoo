import json

from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestOrdersApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_user = new_test_user(cls.env, login="shop_bot", groups="sales_team.group_sale_salesman")
        cls.api_key = cls.env["res.users.apikeys"].with_user(cls.api_user)._generate("rpc", "Tienda en línea")
        cls.customer = cls.env["res.partner"].create({"name": "Cliente API", "vat": "J123456789"})
        cls.product = cls.env["product.product"].create({
            "name": "Producto API", "default_code": "API-001", "list_price": 10.0,
        })

    def setUp(self):
        super().setUp()
        self.authenticate(None, None) 

    def _post(self, payload, key=None, raw=None, extra_headers=None):
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
        headers.update(extra_headers or {})
        data = raw if raw is not None else json.dumps(payload)
        response = self.url_open("/api/v1/orders", data=data, headers=headers)
        return response, response.json()

    def _payload(self, **overrides):
        payload = {
            "customer_vat": "J123456789",
            "external_reference": "WEB-1001",
            "lines": [{"default_code": "API-001", "quantity": 2}],
        }
        payload.update(overrides)
        return payload

    def test_creates_quotation_as_api_user(self):
        response, body = self._post(self._payload(), self.api_key)
        self.assertEqual(response.status_code, 201)
        order = self.env["sale.order"].browse(body["data"]["id"])
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.client_order_ref, "WEB-1001")
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(order.user_id, self.api_user) 
        self.assertEqual(order.order_line.product_uom_qty, 2)

    def test_missing_key_returns_401(self):
        response, body = self._post(self._payload())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")

    def test_wrong_key_returns_401(self):
        response, _body = self._post(self._payload(), "clave-falsa")
        self.assertEqual(response.status_code, 401)

    def test_unknown_product_returns_422_with_field(self):
        lines = [{"default_code": "API-001", "quantity": 1}, {"default_code": "NO-EXISTE", "quantity": 1}]
        response, body = self._post(self._payload(lines=lines), self.api_key)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["error"]["code"], "PRODUCT_NOT_FOUND")
        self.assertEqual(body["error"]["field"], "lines[1].default_code")
        self.assertFalse(self.env["sale.order"].search([("client_order_ref", "=", "WEB-1001")]))

    def test_unknown_customer_returns_422(self):
        response, body = self._post(self._payload(customer_vat="V000"), self.api_key)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["error"]["field"], "customer_vat")

    def test_invalid_quantity_returns_422(self):
        lines = [{"default_code": "API-001", "quantity": True}]
        response, body = self._post(self._payload(lines=lines), self.api_key)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(body["error"]["field"], "lines[0].quantity")

    def test_invalid_json_returns_400(self):
        response, body = self._post(None, self.api_key, raw="{esto no es json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "INVALID_JSON")

    def test_calls_are_logged_without_key(self):
        self._post(self._payload(), self.api_key)
        self._post(self._payload(), "clave-falsa")
        logs = self.env["shop.api.log"].search([("endpoint", "=", "/api/v1/orders")], order="id")
        self.assertEqual(logs.mapped("status_code"), [201, 401])
        self.assertEqual(logs[0].user_id, self.api_user)
        self.assertTrue(logs[0].order_id)
        for log in logs:
            for value in log.read()[0].values():
                self.assertNotIn(self.api_key, str(value))
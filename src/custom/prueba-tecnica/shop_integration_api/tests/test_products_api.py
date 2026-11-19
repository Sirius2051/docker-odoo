from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestProductsApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="shop_api_user", password="shop_api_user",
            groups="sales_team.group_sale_salesman",
        )
        cls.category = cls.env["product.category"].create({"name": "API Ropa"})
        cls.subcategory = cls.env["product.category"].create({"name": "API Camisas", "parent_id": cls.category.id})
        cls.other_category = cls.env["product.category"].create({"name": "API Otros"})

        product_model = cls.env["product.product"]
        cls.with_stock = product_model.create({
            "name": "Camisa con stock", "default_code": "API-STOCK",
            "detailed_type": "product", "categ_id": cls.subcategory.id, "list_price": 15.0,
        })
        cls.without_stock = product_model.create({
            "name": "Camisa sin stock", "default_code": "API-EMPTY",
            "detailed_type": "product", "categ_id": cls.subcategory.id,
        })
        cls.not_for_sale = product_model.create({
            "name": "Insumo interno", "default_code": "API-NOSALE",
            "sale_ok": False, "categ_id": cls.subcategory.id,
        })
        cls.other = product_model.create({
            "name": "Otro producto", "default_code": "API-OTHER", "categ_id": cls.other_category.id,
        })
        stock_location = cls.env.ref("stock.stock_location_stock")
        cls.env["stock.quant"]._update_available_quantity(cls.with_stock, stock_location, 5)

    def setUp(self):
        super().setUp()
        self.authenticate("shop_api_user", "shop_api_user")

    def _get(self, query=""):
        response = self.url_open(f"/api/v1/products{query}")
        return response, response.json()

    def _codes(self, body):
        return {item["default_code"] for item in body["data"]}

    def test_only_saleable_products(self):
        response, body = self._get()
        self.assertEqual(response.status_code, 200)
        codes = self._codes(body)
        self.assertIn("API-STOCK", codes)
        self.assertNotIn("API-NOSALE", codes)

    def test_payload_shape(self):
        _response, body = self._get(f"?category_id={self.subcategory.id}&in_stock=1")
        self.assertEqual(len(body["data"]), 1)
        item = body["data"][0]
        self.assertEqual(item["id"], self.with_stock.id)
        self.assertEqual(item["default_code"], "API-STOCK")
        self.assertEqual(item["name"], "Camisa con stock")
        self.assertEqual(item["price"], 15.0)
        self.assertEqual(item["qty_available"], 5.0)

    def test_filter_category_includes_children(self):
        _response, body = self._get(f"?category_id={self.category.id}")
        self.assertEqual(self._codes(body), {"API-STOCK", "API-EMPTY"})

    def test_filter_in_stock(self):
        _response, body = self._get(f"?category_id={self.subcategory.id}&in_stock=1")
        self.assertEqual(self._codes(body), {"API-STOCK"})

    def test_filter_modified_since(self):
        _response, body = self._get("?modified_since=2999-01-01T00:00:00Z")
        self.assertEqual(body["data"], [])
        _response, body = self._get("?modified_since=2000-01-01")
        self.assertIn("API-STOCK", self._codes(body))

    def test_invalid_date_returns_400(self):
        response, body = self._get("?modified_since=ayer")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "INVALID_DATE")
        self.assertEqual(body["error"]["field"], "modified_since")

    def test_invalid_category_returns_400(self):
        response, body = self._get("?category_id=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["error"]["code"], "INVALID_PARAMETER")

    def test_requires_login_or_api_key(self):
        self.authenticate(None, None)
        response, body = self._get()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body["error"]["code"], "UNAUTHORIZED")

    def test_api_key_gives_access_without_session(self):
        key = self.env["res.users.apikeys"].with_user(self.user)._generate("rpc", "Prueba catálogo")
        self.authenticate(None, None)
        response = self.url_open("/api/v1/products", headers={"Authorization": f"Bearer {key}"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("API-STOCK", self._codes(response.json()))
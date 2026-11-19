from odoo.tests import TransactionCase, tagged

from odoo.addons.shop_integration_api.controllers.main import ShopApiController


@tagged("post_install", "-at_install")
class TestStockQueries(TransactionCase):

    def _queries_to_serialize(self, count):
        products = self.env["product.product"].create([
            {"name": f"Producto {i}", "detailed_type": "product"} for i in range(count)
        ])
        self.env.flush_all()
        self.env.invalidate_all()
        products = self.env["product.product"].browse(products.ids)
        controller = ShopApiController()
        before = self.env.cr.sql_log_count
        for product in products:
            controller._serialize_product(product)
        return self.env.cr.sql_log_count - before

    def test_stock_is_read_in_batch(self):
        with_2 = self._queries_to_serialize(2)
        with_20 = self._queries_to_serialize(20)
        self.assertLessEqual(with_20, with_2 + 2, f"2 productos: {with_2} consultas; 20 productos: {with_20}")
from unittest.mock import MagicMock, patch

import requests

from odoo import fields
from odoo.tests import TransactionCase, tagged

POST = "odoo.addons.shop_integration_api.models.shop_webhook_event.requests.post"


@tagged("post_install", "-at_install")
class TestDeliveryWebhook(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "shop_integration_api.webhook_url", "https://tienda.example/webhooks/odoo",
        )
        cls.partner = cls.env["res.partner"].create({"name": "Cliente webhook"})
        cls.product = cls.env["product.product"].create({"name": "Producto webhook", "detailed_type": "product"})
        stock = cls.env.ref("stock.stock_location_stock")
        cls.env["stock.quant"]._update_available_quantity(cls.product, stock, 10)

    def _validated_delivery(self, shop_origin=True):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "client_order_ref": "WEB-77",
            "shop_origin": shop_origin,
            "order_line": [(0, 0, {"product_id": self.product.id, "product_uom_qty": 2})],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.move_ids.write({"quantity": 2, "picked": True})
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        return order, picking

    def _event_for(self, order):
        return self.env["shop.webhook.event"].search([("order_id", "=", order.id)])

    def test_validation_enqueues_without_calling_the_shop(self):
        with patch(POST) as post:
            order, _picking = self._validated_delivery()
        post.assert_not_called()
        event = self._event_for(order)
        self.assertEqual(event.state, "pending")
        self.assertIn("WEB-77", event.payload)

    def test_orders_not_from_shop_do_not_enqueue(self):
        order, _picking = self._validated_delivery(shop_origin=False)
        self.assertFalse(self._event_for(order))

    def test_retries_then_succeeds(self):
        order, _picking = self._validated_delivery()
        event = self._event_for(order)
        with patch(POST, side_effect=requests.ConnectionError("tienda caída")):
            self.env["shop.webhook.event"]._cron_send_pending()
        self.assertEqual(event.state, "pending")
        self.assertEqual(event.attempts, 1)
        self.assertGreater(event.next_attempt, fields.Datetime.now())
        self.assertIn("tienda caída", event.last_error)

        event.next_attempt = fields.Datetime.now()
        with patch(POST, return_value=MagicMock(status_code=200)) as post:
            self.env["shop.webhook.event"]._cron_send_pending()
        post.assert_called_once()
        self.assertEqual(event.state, "done")
        self.assertEqual(event.attempts, 2)

    def test_gives_up_after_max_attempts(self):
        order, _picking = self._validated_delivery()
        event = self._event_for(order)
        with patch(POST, side_effect=requests.Timeout("sin respuesta")):
            for _attempt in range(6):
                event.next_attempt = fields.Datetime.now()
                self.env["shop.webhook.event"]._cron_send_pending()
        self.assertEqual(event.state, "failed")
        self.assertEqual(event.attempts, 6)
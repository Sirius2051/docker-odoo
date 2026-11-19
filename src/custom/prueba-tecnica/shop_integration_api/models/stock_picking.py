from odoo import models

class StockPicking(models.Model):
    _inherit = "stock.picking"
    def _action_done(self):
        res = super()._action_done()
        deliveries = self.filtered(
            lambda p: p.state == "done" and p.picking_type_code == "outgoing" and p.sale_id.shop_origin
        )
        if deliveries:
            self.env["shop.webhook.event"].sudo()._enqueue_delivery_done(deliveries)
        return res
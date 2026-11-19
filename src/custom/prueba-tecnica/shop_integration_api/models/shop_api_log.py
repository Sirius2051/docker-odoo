from datetime import timedelta
from odoo import api, fields, models

class ShopApiLog(models.Model):
    _name = "shop.api.log"
    _description = "Registro de llamadas a la API de la tienda"
    _order = "id desc"
    _rec_name = "endpoint"

    endpoint = fields.Char(string="Endpoint", required=True)
    method = fields.Char(string="Método")
    user_id = fields.Many2one("res.users", string="Usuario", ondelete="set null")
    status_code = fields.Integer(string="Código HTTP")
    error_code = fields.Char(string="Código de error")
    duration_ms = fields.Float(string="Duración (ms)", digits=(16, 1))
    order_id = fields.Many2one("sale.order", string="Pedido", ondelete="set null")

    @api.autovacuum
    def _gc_old_logs(self):
        limit = fields.Datetime.now() - timedelta(days=90)
        self.search([("create_date", "<", limit)]).unlink()
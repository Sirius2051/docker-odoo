from odoo import fields, models

class ShopApiIdempotency(models.Model):
    _name = "shop.api.idempotency"
    _description = "Claves de idempotencia de la API de la tienda"

    key = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade")
    request_hash = fields.Char(required=True, help="SHA-256 del cuerpo de la petición, con las claves ordenadas.")
    order_id = fields.Many2one("sale.order", ondelete="set null")
    response_status = fields.Integer()
    response_body = fields.Text()

    _sql_constraints = [
        ("key_user_uniq", "unique(key, user_id)", "La clave de idempotencia ya fue usada."),
    ]

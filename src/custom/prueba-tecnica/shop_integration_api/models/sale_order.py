from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    shop_origin = fields.Boolean(
        string="Creado por la tienda en línea", readonly=True, copy=False,
        help="Marca los pedidos creados por la API: solo esos disparan el webhook de entrega.",
    )

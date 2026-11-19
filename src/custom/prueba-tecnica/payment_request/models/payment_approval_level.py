from odoo import fields, models


class PaymentApprovalLevel(models.Model):
    _name = "payment.approval.level"
    _description = "Nivel de aprobación de solicitudes de pago"
    _order = "company_id, min_amount desc"

    name = fields.Char(string="Nombre", required=True)
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", string="Moneda")
    min_amount = fields.Monetary(
        string="Monto mínimo", required=True,
        help="En la moneda de la compañía. Se aplica el nivel de mayor monto mínimo que no supere el monto de la solicitud.",
    )
    approver_id = fields.Many2one(
        "res.users", string="Aprobador", required=True,
        domain=lambda self: [("groups_id", "in", self.env.ref("payment_request.group_payment_request_approver").id)],
    )

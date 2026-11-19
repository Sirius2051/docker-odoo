from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

# Campos de negocio que no se pueden cambiar después de enviar la solicitud.
LOCKED_FIELDS = {"partner_id", "requester_id", "amount", "currency_id", "date", "concept", "company_id"}

# Qué grupo puede llevar una solicitud a cada estado. Lo revisa write(), para que nadie
# se salte los botones llamando write({"state": ...}) por RPC.
STATE_GROUPS = {
    "approved": "payment_request.group_payment_request_approver",
    "rejected": "payment_request.group_payment_request_approver",
    "paid": "payment_request.group_payment_request_treasury",
}


class PaymentRequest(models.Model):
    _name = "payment.request"
    _description = "Solicitud de pago"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Número", required=True, copy=False, readonly=True, default="/")
    partner_id = fields.Many2one("res.partner", string="Proveedor", required=True, tracking=True)
    requester_id = fields.Many2one(
        "res.users", string="Solicitante", required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency", string="Moneda", required=True, tracking=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(string="Monto", required=True, tracking=True)
    date = fields.Date(string="Fecha", required=True, default=fields.Date.context_today)
    concept = fields.Text(string="Concepto", required=True)
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("submitted", "Enviada"),
            ("approved", "Aprobada"),
            ("paid", "Pagada"),
            ("rejected", "Rechazada"),
        ],
        string="Estado", required=True, default="draft", tracking=True, copy=False,
    )
    approved_by_id = fields.Many2one("res.users", string="Aprobada por", readonly=True, copy=False)
    approved_date = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)

    # ---------------------------------------------------------------- ORM
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "payment.request", sequence_date=vals.get("date"),
                ) or "/"
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and any(request.state != "draft" for request in self):
            raise UserError(_("Solo se pueden modificar solicitudes en borrador."))
        group = STATE_GROUPS.get(vals.get("state"))
        if group and not self.env.su and not self.env.user.has_group(group):
            raise AccessError(_("No tienes permiso para cambiar la solicitud a ese estado."))
        return super().write(vals)

    def unlink(self):
        if any(request.state != "draft" for request in self):
            raise UserError(_("Solo se pueden eliminar solicitudes en borrador."))
        return super().unlink()

    @api.constrains("amount")
    def _check_amount(self):
        for request in self:
            if request.currency_id.compare_amounts(request.amount, 0.0) <= 0:
                raise ValidationError(_("El monto debe ser mayor que cero."))

    # ------------------------------------------------------------ helpers
    def _check_state(self, *allowed_states):
        labels = dict(self._fields["state"].selection)
        for request in self:
            if request.state not in allowed_states:
                raise UserError(_(
                    "La solicitud %(name)s está en estado «%(state)s» y no admite esta acción.",
                    name=request.name, state=labels[request.state],
                ))

    def _check_group(self, xmlid):
        if not self.env.user.has_group(xmlid):
            raise AccessError(_("No tienes permiso para realizar esta acción."))

    # ------------------------------------------------------------ actions
    def action_submit(self):
        self._check_state("draft")
        self.write({"state": "submitted"})

    def action_approve(self):
        self._check_group("payment_request.group_payment_request_approver")
        self._check_state("submitted")
        for request in self:
            if request.requester_id == self.env.user:
                raise UserError(_("No puedes aprobar tu propia solicitud."))
        self.write({
            "state": "approved",
            "approved_by_id": self.env.user.id,
            "approved_date": fields.Datetime.now(),
        })

    def action_reject(self):
        self._check_group("payment_request.group_payment_request_approver")
        self._check_state("submitted")
        self.write({"state": "rejected"})

    def action_mark_paid(self):
        """Tramo A: tesorería la marca como pagada. En el tramo B lo reemplaza el asistente de pago."""
        self._check_group("payment_request.group_payment_request_treasury")
        self._check_state("approved")
        self.write({"state": "paid"})

    def action_reset_to_draft(self):
        self._check_state("rejected")
        for request in self:
            if request.requester_id != self.env.user and not self.env.user.has_group(
                "payment_request.group_payment_request_approver"
            ):
                raise AccessError(_("Solo el solicitante puede volver a borrador su solicitud."))
        self.write({"state": "draft"})

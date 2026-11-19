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

TODO_ACTIVITY = "mail.mail_activity_data_todo"


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
    approver_id = fields.Many2one(
        "res.users", string="Aprobador asignado", readonly=True, copy=False, tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", string="Aprobada por", readonly=True, copy=False)
    approved_date = fields.Datetime(string="Fecha de aprobación", readonly=True, copy=False)
    rejection_reason = fields.Text(string="Motivo del rechazo", readonly=True, copy=False)
    payment_id = fields.Many2one("account.payment", string="Pago", readonly=True, copy=False)

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

    def _check_is_assigned_approver(self):
        self._check_group("payment_request.group_payment_request_approver")
        for request in self:
            if request.approver_id != self.env.user:
                raise AccessError(_(
                    "Solo %s puede aprobar o rechazar la solicitud %s.",
                    request.approver_id.name or _("el aprobador asignado"), request.name,
                ))

    def _amount_in_company_currency(self):
        self.ensure_one()
        return self.currency_id._convert(self.amount, self.company_id.currency_id, self.company_id, self.date)

    def _find_approval_level(self):
        self.ensure_one()
        return self.env["payment.approval.level"].search([
            ("company_id", "=", self.company_id.id),
            ("min_amount", "<=", self._amount_in_company_currency()),
        ], order="min_amount desc", limit=1)

    # ------------------------------------------------------------ actions
    def action_submit(self):
        self._check_state("draft")
        for request in self:
            # sudo() justificado: el solicitante no necesita leer la configuración de niveles;
            # solo se consulta para asignar el aprobador.
            level = request.sudo()._find_approval_level()
            if not level:
                raise UserError(_("No hay un nivel de aprobación configurado para este monto."))
            request.write({"state": "submitted", "approver_id": level.approver_id.id})
            request.activity_schedule(
                TODO_ACTIVITY,
                user_id=level.approver_id.id,
                summary=_("Aprobar la solicitud de pago %s", request.name),
            )

    def action_approve(self):
        self._check_is_assigned_approver()
        self._check_state("submitted")
        for request in self:
            if request.requester_id == self.env.user:
                raise UserError(_("No puedes aprobar tu propia solicitud."))
        self.write({
            "state": "approved",
            "approved_by_id": self.env.user.id,
            "approved_date": fields.Datetime.now(),
        })
        self.activity_feedback([TODO_ACTIVITY], feedback=_("Aprobada"))

    def action_reject(self):
        """Abre el asistente de rechazo (el motivo es obligatorio)."""
        self.ensure_one()
        self._check_is_assigned_approver()
        self._check_state("submitted")
        return {
            "type": "ir.actions.act_window",
            "name": _("Rechazar solicitud"),
            "res_model": "payment.request.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def _action_reject(self, reason):
        self._check_is_assigned_approver()
        self._check_state("submitted")
        self.write({"state": "rejected", "rejection_reason": reason})
        for request in self:
            request.message_post(
                body=_("Solicitud rechazada. Motivo: %s", reason),
                subtype_xmlid="mail.mt_comment",
            )
        self.activity_feedback([TODO_ACTIVITY], feedback=_("Rechazada"))

    def action_pay(self):
        """Abre el asistente de pago (tesorería elige el diario y la fecha)."""
        self.ensure_one()
        self._check_group("payment_request.group_payment_request_treasury")
        self._check_state("approved")
        return {
            "type": "ir.actions.act_window",
            "name": _("Pagar solicitud"),
            "res_model": "payment.request.pay.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def _action_pay(self, journal, payment_date):
        self.ensure_one()
        self._check_group("payment_request.group_payment_request_treasury")
        if self.state != "approved" or self.payment_id:
            raise UserError(_("La solicitud %s ya fue pagada o no está aprobada.", self.name))
        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.partner_id.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "journal_id": journal.id,
            "date": payment_date,
            "ref": self.name,
        })
        payment.action_post()
        self.write({"payment_id": payment.id, "state": "paid"})
        self.message_post(body=_("Pagada con %s.", payment.name))
        return payment

    def action_reset_to_draft(self):
        self._check_state("rejected")
        for request in self:
            if request.requester_id != self.env.user and not self.env.user.has_group(
                "payment_request.group_payment_request_approver"
            ):
                raise AccessError(_("Solo el solicitante puede volver a borrador su solicitud."))
        self.write({"state": "draft", "approver_id": False, "rejection_reason": False})

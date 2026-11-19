import logging
from datetime import timedelta
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import sql

_logger = logging.getLogger(__name__)

LEGACY_VEHICLE_TYPE_COLUMN = "vehicle_type"

class FleetInspection(models.Model):
    _name = "fleet.inspection"
    _description = "Inspección de vehículo"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    def _default_vehicle_type(self):
        return self.env.ref("fleet_inspection.vehicle_type_car", raise_if_not_found=False)

    name = fields.Char(string="Número", required=True, copy=False, readonly=True, default="/")
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehículo",
        required=True,
        tracking=True,
    )
    vehicle_type_id = fields.Many2one(
        "fleet.inspection.vehicle.type",
        string="Tipo de vehículo",
        required=True,
        ondelete="restrict",
        default=_default_vehicle_type,
        tracking=True,
    )
    inspector_id = fields.Many2one(
        "res.users",
        string="Inspector",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    date = fields.Date(
        string="Fecha", required=True, default=fields.Date.context_today, tracking=True
    )
    odometer = fields.Float(string="Kilometraje")
    line_ids = fields.One2many(
        "fleet.inspection.line", "inspection_id", string="Checklist", copy=True
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("in_progress", "En curso"),
            ("approved", "Aprobada"),
            ("rejected", "Rechazada"),
        ],
        string="Estado",
        default="draft",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="Observaciones")
    failed_count = fields.Integer(string="Puntos fallidos", compute="_compute_counts", store=True)
    pending_count = fields.Integer(string="Puntos pendientes", compute="_compute_counts", store=True)
    is_overdue = fields.Boolean(string="Vencida", readonly=True, copy=False)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "El número de la inspección debe ser único."),
    ]

    @api.depends("line_ids.result")
    def _compute_counts(self):
        for inspection in self:
            inspection.failed_count = len(inspection.line_ids.filtered(lambda l: l.result == "fail"))
            inspection.pending_count = len(inspection.line_ids.filtered(lambda l: not l.result))

    @api.depends("name", "vehicle_id.license_plate", "vehicle_id.name")
    def _compute_display_name(self):
        for inspection in self:
            vehicle = inspection.vehicle_id
            if vehicle:
                inspection.display_name = f"{inspection.name} - {vehicle.license_plate or vehicle.name}"
            else:
                inspection.display_name = inspection.name

    @api.constrains("odometer")
    def _check_odometer(self):
        for inspection in self:
            if inspection.odometer < 0:
                raise ValidationError(_("El kilometraje no puede ser negativo."))

    @api.model_create_multi
    def create(self, vals_list):
        items = None
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("fleet.inspection") or "/"
            if not vals.get("line_ids"):
                if items is None:
                    items = self.env["fleet.inspection.item"].search([])
                vals["line_ids"] = [Command.create({"item_id": item.id}) for item in items]
        return super().create(vals_list)

    def action_start(self):
        for inspection in self:
            if not inspection.line_ids:
                raise UserError(_("La inspección %s no tiene puntos en el checklist.", inspection.name))
        self.write({"state": "in_progress"})

    def action_approve(self):
        for inspection in self:
            if inspection.pending_count:
                raise UserError(_("Faltan puntos por revisar en la inspección %s.", inspection.name))
            critical_failed = inspection.line_ids.filtered(lambda l: l.result == "fail" and l.item_id.critical)
            if critical_failed:
                raise UserError(_(
                    "No se puede aprobar: fallaron puntos críticos (%s).",
                    ", ".join(critical_failed.mapped("item_id.name")),
                ))
        self.write({"state": "approved", "is_overdue": False})

    def action_reject(self):
        self.write({"state": "rejected", "is_overdue": False})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def unlink(self):
        if any(inspection.state != "draft" for inspection in self):
            raise UserError(_("Solo se pueden eliminar inspecciones en borrador."))
        return super().unlink()

    @api.model
    def _cron_mark_overdue(self, days=7):
        limit_date = fields.Date.context_today(self) - timedelta(days=days)
        overdue = self.search([("state", "=", "in_progress"), ("date", "<", limit_date), ("is_overdue", "=", False)])
        overdue.write({"is_overdue": True})
        for inspection in overdue:
            inspection.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=inspection.inspector_id.id,
                summary=_("Inspección en curso desde hace más de %s días", days),
            )
        return True

    @api.model
    def _migrate_legacy_vehicle_type(self, batch_size=5000):
        cr = self.env.cr
        if not sql.column_exists(cr, self._table, LEGACY_VEHICLE_TYPE_COLUMN):
            return 0

        cr.execute(f"SELECT COALESCE(MIN(id), 0), COALESCE(MAX(id), 0) FROM {self._table}")
        min_id, max_id = cr.fetchone()
        converted = 0
        for start in range(min_id, max_id + 1, batch_size):
            end = start + batch_size - 1
            cr.execute(
                f"""
                UPDATE {self._table} AS inspection
                   SET vehicle_type_id = vehicle_type.id
                  FROM fleet_inspection_vehicle_type AS vehicle_type
                 WHERE inspection.id BETWEEN %s AND %s
                   AND inspection.vehicle_type_id IS NULL
                   AND vehicle_type.code = inspection.{LEGACY_VEHICLE_TYPE_COLUMN}
                """,
                [start, end],
            )
            converted += cr.rowcount

        other = self.env.ref("fleet_inspection.vehicle_type_other")
        cr.execute(
            f"UPDATE {self._table} SET vehicle_type_id = %s WHERE vehicle_type_id IS NULL",
            [other.id],
        )
        if cr.rowcount:
            _logger.warning(
                "fleet_inspection: %s inspecciones sin tipo reconocible quedaron como 'Otro'", cr.rowcount,
            )
        converted += cr.rowcount
        self.invalidate_model(["vehicle_type_id"])
        return converted
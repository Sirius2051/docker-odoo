from odoo import fields, models

class FleetInspectionVehicleType(models.Model):
    _name = "fleet.inspection.vehicle.type"
    _description = "Tipo de vehículo para inspecciones"
    _order = "sequence, id"

    name = fields.Char(string="Nombre", required=True, translate=True)
    code = fields.Char(
        string="Código",
        required=True,
        help="Identificador técnico estable. Coincide con el valor de la antigua selección.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_uniq", "unique(code)", "El código del tipo de vehículo debe ser único."),
    ]
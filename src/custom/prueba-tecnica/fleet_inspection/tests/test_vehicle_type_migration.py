import logging
import time
from psycopg2 import IntegrityError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

_logger = logging.getLogger(__name__)

@tagged("post_install", "-at_install")
class TestVehicleTypeMigration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Marca migración"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Modelo migración", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "MIG001"})
        cls.type_car = cls.env.ref("fleet_inspection.vehicle_type_car")
        cls.type_truck = cls.env.ref("fleet_inspection.vehicle_type_truck")
        cls.type_other = cls.env.ref("fleet_inspection.vehicle_type_other")

    def _prepare_legacy_schema(self):
        cr = self.env.cr
        cr.execute("ALTER TABLE fleet_inspection ADD COLUMN IF NOT EXISTS vehicle_type varchar")
        cr.execute("ALTER TABLE fleet_inspection ALTER COLUMN vehicle_type_id DROP NOT NULL")

    def _simulate_legacy_rows(self, legacy_values):
        inspections = self.env["fleet.inspection"].create([
            {"vehicle_id": self.vehicle.id} for _value in legacy_values
        ])
        self._prepare_legacy_schema()
        for inspection, value in zip(inspections, legacy_values):
            self.env.cr.execute(
                "UPDATE fleet_inspection SET vehicle_type = %s, vehicle_type_id = NULL WHERE id = %s",
                [value, inspection.id],
            )
        inspections.invalidate_recordset()
        return inspections

    def test_maps_each_legacy_value(self):
        car, truck, other = self._simulate_legacy_rows(["car", "truck", "other"])
        self.env["fleet.inspection"]._migrate_legacy_vehicle_type()
        self.assertEqual(car.vehicle_type_id, self.type_car)
        self.assertEqual(truck.vehicle_type_id, self.type_truck)
        self.assertEqual(other.vehicle_type_id, self.type_other)

    def test_unknown_or_empty_values_become_other(self):
        unknown, empty = self._simulate_legacy_rows(["bus", None])
        with mute_logger("odoo.addons.fleet_inspection.models.fleet_inspection"):
            self.env["fleet.inspection"]._migrate_legacy_vehicle_type()
        self.assertEqual(unknown.vehicle_type_id, self.type_other)
        self.assertEqual(empty.vehicle_type_id, self.type_other)

    def test_is_idempotent(self):
        (truck,) = self._simulate_legacy_rows(["truck"])
        first = self.env["fleet.inspection"]._migrate_legacy_vehicle_type()
        second = self.env["fleet.inspection"]._migrate_legacy_vehicle_type()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(truck.vehicle_type_id, self.type_truck)

    def test_small_batches_convert_everything(self):
        inspections = self._simulate_legacy_rows(["car", "truck"] * 5)
        self.env["fleet.inspection"]._migrate_legacy_vehicle_type(batch_size=3)
        self.assertFalse(inspections.filtered(lambda i: not i.vehicle_type_id))

    def test_without_legacy_column_does_nothing(self):
        self.assertEqual(self.env["fleet.inspection"]._migrate_legacy_vehicle_type(), 0)

    def test_type_is_required(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["fleet.inspection"].create({"vehicle_id": self.vehicle.id, "vehicle_type_id": False})

    def test_migrates_10000_rows_in_batches(self):
        self._prepare_legacy_schema()
        self.env.cr.execute(
            """
            INSERT INTO fleet_inspection (name, vehicle_id, inspector_id, date, state, vehicle_type)
            SELECT 'BULK/' || g, %s, %s, CURRENT_DATE, 'draft',
                   (ARRAY['motorcycle', 'car', 'truck', 'other'])[1 + g %% 4]
              FROM generate_series(1, 10000) AS g
            """,
            [self.vehicle.id, self.env.uid],
        )
        started = time.perf_counter()
        converted = self.env["fleet.inspection"]._migrate_legacy_vehicle_type(batch_size=1000)
        elapsed = time.perf_counter() - started
        _logger.info("fleet_inspection: 10000 filas migradas en lotes de 1000 en %.3f s", elapsed)

        self.assertEqual(converted, 10000)
        self.env.cr.execute("SELECT count(*) FROM fleet_inspection WHERE vehicle_type_id IS NULL")
        self.assertEqual(self.env.cr.fetchone()[0], 0)
        self.env.cr.execute(
            """SELECT count(*) FROM fleet_inspection fi
                 JOIN fleet_inspection_vehicle_type t ON t.id = fi.vehicle_type_id
                WHERE fi.name LIKE 'BULK/%%' AND t.code = 'other'"""
        )
        self.assertEqual(self.env.cr.fetchone()[0], 2500)
        self.assertLess(elapsed, 60, "La migración de 10 000 filas no debería tardar un minuto")
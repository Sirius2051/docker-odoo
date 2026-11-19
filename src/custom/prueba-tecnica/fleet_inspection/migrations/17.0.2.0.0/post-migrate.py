import logging
import time
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    if not version:
        return 
    env = api.Environment(cr, SUPERUSER_ID, {})
    started = time.perf_counter()
    converted = env["fleet.inspection"]._migrate_legacy_vehicle_type()
    _logger.info(
        "fleet_inspection 17.0.2.0.0: %s inspecciones convertidas al catálogo de tipos en %.3f s",
        converted, time.perf_counter() - started,
    )
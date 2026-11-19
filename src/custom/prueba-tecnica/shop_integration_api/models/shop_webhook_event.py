import json
import logging
from datetime import timedelta
import requests
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

WEBHOOK_URL_PARAM = "shop_integration_api.webhook_url"
BACKOFF_MINUTES = [1, 5, 15, 60, 240] 
MAX_ATTEMPTS = len(BACKOFF_MINUTES) + 1


class ShopWebhookEvent(models.Model):
    _name = "shop.webhook.event"
    _description = "Evento pendiente de enviar a la tienda en línea"
    _order = "next_attempt, id"

    event_type = fields.Char(required=True)
    order_id = fields.Many2one("sale.order", ondelete="cascade")
    picking_id = fields.Many2one("stock.picking", ondelete="cascade")
    payload = fields.Text(required=True)
    state = fields.Selection(
        [("pending", "Pendiente"), ("done", "Enviado"), ("failed", "Fallido")],
        required=True, default="pending", index=True,
    )
    attempts = fields.Integer(default=0)
    next_attempt = fields.Datetime(default=fields.Datetime.now, index=True)
    last_error = fields.Char()
    sent_at = fields.Datetime()

    @api.model
    def _enqueue_delivery_done(self, pickings):
        self.create([{
            "event_type": "delivery.done",
            "order_id": picking.sale_id.id,
            "picking_id": picking.id,
            "payload": json.dumps({
                "event": "delivery.done",
                "order_id": picking.sale_id.id,
                "order_name": picking.sale_id.name,
                "external_reference": picking.sale_id.client_order_ref,
                "delivery": picking.name,
                "date_done": fields.Datetime.to_string(picking.date_done),
            }),
        } for picking in pickings])

    @api.model
    def _cron_send_pending(self, limit=50):
        url = self.env["ir.config_parameter"].sudo().get_param(WEBHOOK_URL_PARAM)
        if not url:
            return
        events = self.search(
            [("state", "=", "pending"), ("next_attempt", "<=", fields.Datetime.now())], limit=limit,
        )
        for event in events:
            event._send(url)

    def _send(self, url):
        self.ensure_one()
        attempts = self.attempts + 1
        try:
            response = requests.post(
                url,
                data=self.payload,
                headers={"Content-Type": "application/json", "X-Shop-Event": self.event_type},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            if attempts >= MAX_ATTEMPTS:
                self.write({"state": "failed", "attempts": attempts, "last_error": str(error)[:500]})
                _logger.error("Webhook %s falló definitivamente tras %s intentos: %s", self.id, attempts, error)
            else:
                self.write({
                    "attempts": attempts,
                    "next_attempt": fields.Datetime.now() + timedelta(minutes=BACKOFF_MINUTES[attempts - 1]),
                    "last_error": str(error)[:500],
                })
                _logger.warning("Webhook %s falló (intento %s), se reintenta: %s", self.id, attempts, error)
        else:
            self.write({"state": "done", "attempts": attempts, "sent_at": fields.Datetime.now(), "last_error": False})
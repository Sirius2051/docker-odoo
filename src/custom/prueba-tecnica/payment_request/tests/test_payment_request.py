from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestPaymentRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(cls.env, login="pr_requester", groups="base.group_user")
        cls.other_requester = new_test_user(cls.env, login="pr_other", groups="base.group_user")
        cls.approver = new_test_user(
            cls.env, login="pr_approver", groups="payment_request.group_payment_request_approver",
        )
        cls.big_approver = new_test_user(
            cls.env, login="pr_big_approver", groups="payment_request.group_payment_request_approver",
        )
        cls.treasurer = new_test_user(
            cls.env, login="pr_treasurer", groups="payment_request.group_payment_request_treasury",
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Proveedor de prueba"})
        levels = cls.env["payment.approval.level"]
        cls.level_general = levels.create({"name": "General", "min_amount": 0.0, "approver_id": cls.approver.id})
        cls.level_big = levels.create({"name": "Gerencia", "min_amount": 5000.0, "approver_id": cls.big_approver.id})

    def _new_request(self, user=None, **vals):
        values = {"partner_id": self.vendor.id, "amount": 100.0, "concept": "Repuestos"}
        values.update(vals)
        return self.env["payment.request"].with_user(user or self.requester).create(values)

    def _submitted_request(self, **vals):
        request = self._new_request(**vals)
        request.action_submit()
        return request

    # --- flujo
    def test_flow_until_approved(self):
        request = self._submitted_request()
        self.assertTrue(request.name.startswith("SP/"))
        self.assertEqual(request.requester_id, self.requester)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(request.approved_by_id, self.approver)
        self.assertTrue(request.approved_date)

    def test_sequence_uses_request_year(self):
        request = self._new_request(date="2025-12-31")
        self.assertTrue(request.name.startswith("SP/2025/"))

    # --- niveles y actividad (tramo B)
    def test_submit_assigns_approver_by_amount(self):
        small = self._submitted_request(amount=100.0)
        big = self._submitted_request(amount=20000.0)
        self.assertEqual(small.approver_id, self.approver)
        self.assertEqual(big.approver_id, self.big_approver)

    def test_submit_creates_activity_for_approver(self):
        request = self._submitted_request()
        self.assertEqual(request.activity_ids.user_id, self.approver)
        request.with_user(self.approver).action_approve()
        self.assertFalse(request.activity_ids)

    def test_only_assigned_approver_can_approve(self):
        request = self._submitted_request(amount=20000.0)
        with self.assertRaises(AccessError):
            request.with_user(self.approver).action_approve()
        request.with_user(self.big_approver).action_approve()
        self.assertEqual(request.state, "approved")

    def test_submit_without_level_fails(self):
        self.level_general.unlink()
        with self.assertRaises(UserError):
            self._submitted_request(amount=100.0)

    # --- rechazo (tramo B)
    def test_reject_wizard_posts_reason(self):
        request = self._submitted_request()
        wizard = self.env["payment.request.reject.wizard"].with_user(self.approver).create({
            "request_id": request.id, "reason": "Falta la factura del proveedor",
        })
        wizard.action_confirm()
        self.assertEqual(request.state, "rejected")
        self.assertEqual(request.rejection_reason, "Falta la factura del proveedor")
        self.assertTrue(any("Falta la factura del proveedor" in str(m.body) for m in request.message_ids))
        request.action_reset_to_draft()
        self.assertEqual(request.state, "draft")
        self.assertFalse(request.approver_id)

    def test_reject_reason_is_required(self):
        request = self._submitted_request()
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["payment.request.reject.wizard"].with_user(self.approver).create({
                "request_id": request.id, "reason": False,
            })
        self.assertEqual(request.state, "submitted")

    # --- lo que el solicitante no puede hacer
    def test_requester_sees_only_own(self):
        own = self._new_request()
        other = self._new_request(user=self.other_requester)
        visible = self.env["payment.request"].with_user(self.requester).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)
        self.assertIn(other, self.env["payment.request"].with_user(self.approver).search([]))

    def test_requester_cannot_approve_by_method(self):
        request = self._submitted_request()
        with self.assertRaises(AccessError):
            request.action_approve()

    def test_requester_cannot_approve_by_write(self):
        request = self._submitted_request()
        with self.assertRaises(AccessError):
            request.write({"state": "approved"})

    def test_approver_cannot_approve_own_request(self):
        request = self._new_request(user=self.approver)
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_approve()

    def test_submitted_request_is_locked(self):
        request = self._submitted_request()
        with self.assertRaises(UserError):
            request.write({"amount": 999.0})

    def test_amount_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._new_request(amount=0.0)
        with self.assertRaises(ValidationError):
            self._new_request(amount=-5.0)

    def test_treasury_cannot_pay_unapproved(self):
        request = self._submitted_request()
        with self.assertRaises(UserError):
            request.with_user(self.treasurer)._action_pay(self.env["account.journal"], "2026-11-20")

    def test_cannot_delete_submitted(self):
        request = self._submitted_request()
        with self.assertRaises(UserError):
            request.unlink()

    # --- botones según el grupo
    def test_approve_button_hidden_for_requester(self):
        def form_arch(user):
            views = self.env["payment.request"].with_user(user).get_views([(False, "form")])
            return views["views"]["form"]["arch"]
        self.assertNotIn('name="action_approve"', form_arch(self.requester))
        self.assertIn('name="action_approve"', form_arch(self.approver))
        self.assertNotIn('name="action_pay"', form_arch(self.approver))
        self.assertIn('name="action_pay"', form_arch(self.treasurer))

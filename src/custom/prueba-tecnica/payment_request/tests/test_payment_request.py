from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


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
        cls.treasurer = new_test_user(
            cls.env, login="pr_treasurer", groups="payment_request.group_payment_request_treasury",
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Proveedor de prueba"})

    def _new_request(self, user=None, **vals):
        values = {"partner_id": self.vendor.id, "amount": 100.0, "concept": "Repuestos"}
        values.update(vals)
        return self.env["payment.request"].with_user(user or self.requester).create(values)

    # --- flujo
    def test_full_flow(self):
        request = self._new_request()
        self.assertTrue(request.name.startswith("SP/"))
        self.assertEqual(request.requester_id, self.requester)
        request.action_submit()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertEqual(request.approved_by_id, self.approver)
        request.with_user(self.treasurer).action_mark_paid()
        self.assertEqual(request.state, "paid")

    def test_sequence_uses_request_year(self):
        request = self._new_request(date="2025-12-31")
        self.assertTrue(request.name.startswith("SP/2025/"))

    def test_reject_and_reset(self):
        request = self._new_request()
        request.action_submit()
        request.with_user(self.approver).action_reject()
        self.assertEqual(request.state, "rejected")
        request.action_reset_to_draft()
        self.assertEqual(request.state, "draft")

    # --- lo que el solicitante no puede hacer
    def test_requester_sees_only_own(self):
        own = self._new_request()
        other = self._new_request(user=self.other_requester)
        visible = self.env["payment.request"].with_user(self.requester).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)
        self.assertIn(other, self.env["payment.request"].with_user(self.approver).search([]))

    def test_requester_cannot_approve_by_method(self):
        request = self._new_request()
        request.action_submit()
        with self.assertRaises(AccessError):
            request.action_approve()

    def test_requester_cannot_approve_by_write(self):
        request = self._new_request()
        request.action_submit()
        with self.assertRaises(AccessError):
            request.write({"state": "approved"})

    def test_approver_cannot_approve_own_request(self):
        request = self._new_request(user=self.approver)
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_approve()

    def test_submitted_request_is_locked(self):
        request = self._new_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.write({"amount": 999.0})

    def test_amount_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._new_request(amount=0.0)
        with self.assertRaises(ValidationError):
            self._new_request(amount=-5.0)

    def test_treasury_cannot_pay_unapproved(self):
        request = self._new_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.with_user(self.treasurer).action_mark_paid()

    def test_cannot_delete_submitted(self):
        request = self._new_request()
        request.action_submit()
        with self.assertRaises(UserError):
            request.unlink()

    # --- botones según el grupo
    def test_approve_button_hidden_for_requester(self):
        def form_arch(user):
            views = self.env["payment.request"].with_user(user).get_views([(False, "form")])
            return views["views"]["form"]["arch"]
        self.assertNotIn('name="action_approve"', form_arch(self.requester))
        self.assertIn('name="action_approve"', form_arch(self.approver))

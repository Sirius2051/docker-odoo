from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestPaymentRequestPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company = cls.company_data["company"]
        in_company = {"company_id": cls.company.id, "company_ids": [(6, 0, cls.company.ids)]}
        cls.requester = new_test_user(cls.env, login="prp_requester", groups="base.group_user", **in_company)
        cls.approver = new_test_user(
            cls.env, login="prp_approver", groups="payment_request.group_payment_request_approver", **in_company,
        )
        cls.treasurer = new_test_user(
            cls.env, login="prp_treasurer", groups="payment_request.group_payment_request_treasury", **in_company,
        )
        cls.env["payment.approval.level"].create({
            "name": "General", "company_id": cls.company.id, "min_amount": 0.0, "approver_id": cls.approver.id,
        })
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _approved_request(self, **vals):
        values = {"partner_id": self.partner_a.id, "amount": 100.0, "concept": "Servicio"}
        values.update(vals)
        request = self.env["payment.request"].with_user(self.requester).create(values)
        request.action_submit()
        request.with_user(self.approver).action_approve()
        return request

    def test_pay_creates_posted_supplier_payment(self):
        request = self._approved_request()
        wizard = self.env["payment.request.pay.wizard"].with_user(self.treasurer).create({
            "request_id": request.id, "journal_id": self.bank_journal.id, "payment_date": "2026-11-20",
        })
        wizard.action_confirm()
        payment = request.payment_id
        self.assertEqual(request.state, "paid")
        self.assertEqual(payment.state, "posted")
        self.assertEqual(payment.payment_type, "outbound")
        self.assertEqual(payment.partner_type, "supplier")
        self.assertEqual(payment.partner_id, self.partner_a)
        self.assertEqual(payment.amount, 100.0)
        self.assertEqual(payment.ref, request.name)

    def test_cannot_pay_twice(self):
        request = self._approved_request()
        request.with_user(self.treasurer)._action_pay(self.bank_journal, "2026-11-20")
        with self.assertRaises(UserError):
            request.with_user(self.treasurer)._action_pay(self.bank_journal, "2026-11-20")
        self.assertEqual(self.env["account.payment"].search_count([("ref", "=", request.name)]), 1)

    def test_approver_cannot_pay(self):
        request = self._approved_request()
        with self.assertRaises(AccessError):
            request.with_user(self.approver)._action_pay(self.bank_journal, "2026-11-20")
        self.assertFalse(request.payment_id)

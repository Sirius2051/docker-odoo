from unittest.mock import patch

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

    # ------------------------------------------------------------------ tramo C
    def test_usd_request_paid_from_ves_journal_uses_payment_date_rate(self):
        usd = self.company.currency_id  # la compañía de la prueba está en USD
        ves = self.env.ref("base.VES")
        ves.active = True
        self.env["res.currency.rate"].create([
            {"currency_id": ves.id, "company_id": self.company.id, "name": "2026-11-01", "rate": 40.0},
            {"currency_id": ves.id, "company_id": self.company.id, "name": "2026-11-20", "rate": 45.0},
        ])
        ves_journal = self.env["account.journal"].create({
            "name": "Banco en bolívares", "type": "bank", "code": "BVES",
            "currency_id": ves.id, "company_id": self.company.id,
        })
        request = self._approved_request(amount=100.0, currency_id=usd.id, date="2026-11-01")
        payment = request.with_user(self.treasurer)._action_pay(ves_journal, "2026-11-20")
        self.assertEqual(payment.currency_id, ves)
        self.assertAlmostEqual(payment.amount, 4500.0)  # 100 USD x 45 (tasa del día del pago, no la de 40)

    def test_failed_payment_does_not_mark_paid(self):
        request = self._approved_request()
        payment_class = type(self.env["account.payment"])
        with patch.object(payment_class, "action_post", side_effect=UserError("Fallo simulado del banco")):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                request.with_user(self.treasurer)._action_pay(self.bank_journal, "2026-11-20")
        request.invalidate_recordset()
        self.assertEqual(request.state, "approved")
        self.assertFalse(request.payment_id)
        self.assertEqual(self.env["account.payment"].search_count([("ref", "=", request.name)]), 0)

    def test_other_company_user_sees_nothing(self):
        request = self._approved_request()
        company_b = self.company_data_2["company"]
        user_b = new_test_user(
            self.env, login="prp_user_b", groups="payment_request.group_payment_request_approver",
            company_id=company_b.id, company_ids=[(6, 0, company_b.ids)],
        )
        self.assertNotIn(request, self.env["payment.request"].with_user(user_b).search([]))
        self.assertFalse(self.env["payment.approval.level"].with_user(user_b).search([]))

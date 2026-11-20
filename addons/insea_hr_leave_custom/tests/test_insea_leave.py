from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestInseaLeave(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Collaborateur INSEA"})
        cls.exit_type = cls.env.ref("insea_hr_leave_custom.leave_type_short_exit")
        cls.annual_type = cls.env.ref("insea_hr_leave_custom.leave_type_annual")
        cls.first = fields.Date.today().replace(day=1) + timedelta(days=32)
        cls.first = cls.first.replace(day=1)
        while cls.first.weekday() != 0:
            cls.first += timedelta(days=1)

    def _exit(self, day, end_hour="10", reason="administrative"):
        return self.env["hr.leave"].create({
            "employee_id": self.employee.id,
            "holiday_status_id": self.exit_type.id,
            "request_unit_hours": True,
            "request_date_from": day,
            "request_date_to": day,
            "request_hour_from": "8",
            "request_hour_to": end_hour,
            "insea_exit_reason": reason,
        })

    def test_draft_and_standard_submission(self):
        leave = self._exit(self.first)
        self.assertEqual(leave.state, "draft")
        self.assertEqual(leave.insea_exit_hours, 2)
        self.assertEqual(leave.holiday_status_id.requires_allocation, "no")
        leave.action_confirm()
        self.assertEqual(leave.state, "confirm")

    def test_reason_required_at_submission(self):
        leave = self._exit(self.first, reason=False)
        with self.assertRaisesRegex(ValidationError, "motif"), self.cr.savepoint():
            leave.action_confirm()
        self.assertEqual(leave.state, "draft")

    def test_medical_requires_document(self):
        medical = self._exit(self.first, reason="medical")
        ordinary = self._exit(self.first + timedelta(days=1))
        self.assertTrue(medical.insea_needs_attachment)
        self.assertFalse(ordinary.insea_needs_attachment)

    def test_monthly_count_and_month_reset(self):
        for offset in range(3):
            self._exit(self.first + timedelta(days=offset)).action_confirm()
        fourth = self._exit(self.first + timedelta(days=3))
        with self.assertRaisesRegex(ValidationError, "trois autorisations"), self.cr.savepoint():
            fourth.action_confirm()
        next_month = (self.first.replace(day=1) + timedelta(days=32)).replace(day=1)
        while next_month.weekday() >= 5:
            next_month += timedelta(days=1)
        self._exit(next_month).action_confirm()

    def test_monthly_hours_and_four_hour_boundary(self):
        for offset in range(2):
            leave = self._exit(self.first + timedelta(days=offset), end_hour="12")
            self.assertEqual(leave.insea_exit_hours, 4)
            leave.action_confirm()
        third = self._exit(self.first + timedelta(days=2), end_hour="9")
        with self.assertRaisesRegex(ValidationError, "huit heures"), self.cr.savepoint():
            third.action_confirm()

    def test_native_overlap_across_types(self):
        self._exit(self.first).action_confirm()
        sick_type = self.env.ref("insea_hr_leave_custom.leave_type_sickness")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["hr.leave"].create({
                "employee_id": self.employee.id,
                "holiday_status_id": sick_type.id,
                "request_date_from": self.first,
                "request_date_to": self.first,
            })

    def test_standard_accrual_configuration(self):
        plan = self.env.ref("insea_hr_leave_custom.annual_accrual_plan")
        self.assertEqual(plan.time_off_type_id, self.annual_type)
        self.assertTrue(plan.is_based_on_worked_time)
        self.assertEqual(plan.accrued_gain_time, "end")
        self.assertEqual(plan.level_ids.frequency, "monthly")
        self.assertEqual(plan.level_ids.added_value, 1.5)
        self.assertEqual(self.annual_type.requires_allocation, "yes")
        self.assertFalse(self.annual_type.allows_negative)

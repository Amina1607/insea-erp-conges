from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


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

    def _allocate(self, days):
        allocation = self.env["hr.leave.allocation"].create({
            "name": "Allocation de test",
            "employee_id": self.employee.id,
            "holiday_status_id": self.annual_type.id,
            "number_of_days": days,
            "date_from": fields.Date.today(),
        })
        if allocation.state != "validate":
            allocation.action_validate()
        return allocation

    def _annual(self, start, end):
        return self.env["hr.leave"].create({
            "employee_id": self.employee.id,
            "holiday_status_id": self.annual_type.id,
            "request_date_from": start,
            "request_date_to": end,
        })

    def _annual_balance(self, day):
        return self.annual_type.get_allocation_data(self.employee, day)[self.employee][0][1]

    def test_annual_notice_is_checked_at_submission(self):
        self._allocate(10)
        start = fields.Date.today() + timedelta(days=1)
        while start.weekday() >= 5:
            start += timedelta(days=1)
        end = start
        for _unused in range(3):
            end += timedelta(days=1)
            while end.weekday() >= 5:
                end += timedelta(days=1)
        leave = self._annual(start, end)
        self.assertEqual(leave.number_of_days, 4)
        with self.assertRaisesRegex(ValidationError, "sept jours"), self.cr.savepoint():
            leave.action_confirm()
        self.assertEqual(leave.state, "draft")

    def test_annual_balance_exact_and_excess(self):
        self._allocate(1)
        self._exit(self.first).action_confirm()
        day = self.first + timedelta(days=1)
        self.assertEqual(self._annual_balance(day)["virtual_remaining_leaves"], 1)
        leave = self._annual(day, day)
        leave.action_confirm()
        self.assertEqual(self._annual_balance(day)["virtual_remaining_leaves"], 0)
        self.assertEqual(self._annual_balance(day)["remaining_leaves"], 1)
        leave.action_approve()
        self.assertEqual(leave.state, "validate1")
        leave.action_validate()
        self.assertEqual(self._annual_balance(day)["remaining_leaves"], 0)
        later = day + timedelta(days=1)
        extra = self._annual(later, later)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            extra.action_confirm()

    def test_employee_can_submit_using_native_permissions(self):
        employee_user = new_test_user(self.env, login="insea-employee", groups="base.group_user")
        self.employee.user_id = employee_user
        leave = self.env["hr.leave"].with_user(employee_user).create({
            "employee_id": self.employee.id,
            "holiday_status_id": self.exit_type.id,
            "request_unit_hours": True,
            "request_date_from": self.first,
            "request_date_to": self.first,
            "request_hour_from": "8",
            "request_hour_to": "10",
            "insea_exit_reason": "personal",
        })
        self.assertEqual(leave.state, "draft")
        leave.action_confirm()
        self.assertEqual(leave.state, "confirm")

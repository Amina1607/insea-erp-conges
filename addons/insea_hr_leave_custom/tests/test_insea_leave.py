import base64
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
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
        employee_user = self._insea_user("insea-employee")
        manager_user = self._insea_user(
            "insea-employee-manager",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        self.employee.user_id = employee_user
        manager_employee = self.env["hr.employee"].create({
            "name": "Manager de l’employé INSEA",
            "user_id": manager_user.id,
        })
        self.employee.leave_manager_id = manager_user
        leave = self.env["hr.leave"].with_user(employee_user).create({
            "employee_id": self.employee.id,
            "holiday_status_id": self.exit_type.id,
            "request_unit_hours": True,
            "request_date_from": self.first,
            "request_date_to": self.first,
            "request_hour_from": "8",
            "request_hour_to": "10",
            "insea_exit_reason": "administrative",
        })
        self.assertEqual(leave.state, "draft")
        with self.assertRaisesRegex(AccessError, "Seul le collaborateur"):
            leave.with_user(manager_user).action_confirm()
        leave.action_confirm()
        self.assertEqual(leave.state, "confirm")
        leave.with_user(manager_user).action_approve()
        self.assertEqual(leave.state, "validate")

    def test_marriage_requires_four_working_days(self):
        marriage = self.env.ref("insea_hr_leave_custom.leave_type_marriage")
        leave = self.env["hr.leave"].create({
            "employee_id": self.employee.id,
            "holiday_status_id": marriage.id,
            "request_date_from": self.first,
            "request_date_to": self.first + timedelta(days=2),
        })
        self.assertTrue(leave.insea_needs_attachment)
        with self.assertRaisesRegex(ValidationError, "Durée autorisée"), self.cr.savepoint():
            leave.action_confirm()
        leave.request_date_to = self.first + timedelta(days=3)
        leave.action_confirm()
        self.assertEqual(leave.state, "confirm")

    def _insea_user(self, login, groups="base.group_user"):
        return new_test_user(
            self.env,
            login=login,
            groups=groups,
        )

    def test_exact_four_hours_and_over_four_hours(self):
        exact = self._exit(self.first, end_hour="12")
        self.assertEqual(exact.insea_exit_hours, 4)
        exact.action_confirm()
        with self.assertRaises(Exception), self.cr.savepoint():
            self._exit(self.first + timedelta(days=1), end_hour="13")

    def test_exact_eight_hours_is_allowed_but_ninth_is_rejected(self):
        first = self._exit(self.first, end_hour="12")
        second = self._exit(self.first + timedelta(days=1), end_hour="12")
        first.action_confirm()
        second.action_confirm()
        third = self._exit(self.first + timedelta(days=2), end_hour="10")
        with self.assertRaisesRegex(ValidationError, "huit heures"), self.cr.savepoint():
            third.action_confirm()
        fourth = self._exit(self.first + timedelta(days=3), end_hour="11")
        with self.assertRaisesRegex(ValidationError, "huit heures"), self.cr.savepoint():
            fourth.action_confirm()

    def test_manager_short_approval_and_medical_document(self):
        manager_user = self._insea_user(
            "insea-manager",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        manager = self.env["hr.employee"].create({
            "name": "Manager INSEA",
            "user_id": manager_user.id,
        })
        self.employee.leave_manager_id = manager_user
        medical = self._exit(self.first, reason="medical")
        medical.action_confirm()
        with self.assertRaisesRegex(ValidationError, "justificatif"), self.cr.savepoint():
            medical.with_user(manager_user).action_validate()
        self.env["ir.attachment"].create({
            "name": "consultation.pdf",
            "mimetype": "application/pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "hr.leave",
            "res_id": medical.id,
        })
        medical.invalidate_recordset(["supported_attachment_ids"])
        medical.with_user(manager_user).action_approve()
        self.assertEqual(medical.state, "validate")
        self.assertTrue(medical.insea_final_approved)

    def test_paid_leave_manager_then_hr_and_once(self):
        manager_user = self._insea_user(
            "insea-paid-manager",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        hr_user = self._insea_user(
            "insea-paid-hr",
            "base.group_user,hr_holidays.group_hr_holidays_user",
        )
        manager = self.env["hr.employee"].create({
            "name": "Manager payé",
            "user_id": manager_user.id,
        })
        self.employee.leave_manager_id = manager_user
        self._allocate(10)
        leave = self._annual(self.first, self.first)
        leave.action_confirm()
        leave.with_user(manager_user).action_approve()
        self.assertEqual(leave.state, "validate1")
        with self.assertRaises(AccessError):
            leave.with_user(manager_user).action_validate()
        leave.with_user(hr_user).action_validate()
        self.assertEqual(leave.state, "validate")
        self.assertTrue(leave.insea_final_approved)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            leave.with_user(hr_user).action_validate()

    def test_refusal_requires_reason_and_notifies_employee(self):
        manager_user = self._insea_user(
            "insea-refuse-manager",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        manager = self.env["hr.employee"].create({
            "name": "Manager refus",
            "user_id": manager_user.id,
        })
        employee_user = self._insea_user("insea-refuse-employee")
        self.employee.user_id = employee_user
        self.employee.leave_manager_id = manager_user
        leave = self._exit(self.first)
        leave.with_user(employee_user).action_confirm()
        with self.assertRaisesRegex(ValidationError, "motif de refus"), self.cr.savepoint():
            leave.with_user(manager_user).action_refuse()
        leave.insea_refusal_reason = "Horaires incompatibles"
        leave.with_user(manager_user).action_refuse()
        self.assertEqual(leave.state, "refuse")

    def test_employee_cannot_edit_after_submission(self):
        employee_user = self._insea_user("insea-edit-employee")
        self.employee.user_id = employee_user
        leave = self._exit(self.first)
        leave.with_user(employee_user).action_confirm()
        with self.assertRaises(AccessError), self.cr.savepoint():
            leave.with_user(employee_user).write({"insea_exit_reason": "personal"})

    def test_overlap_pending_approved_and_adjacent_request(self):
        first = self._exit(self.first)
        first.action_confirm()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._exit(self.first, end_hour="9")

        adjacent = self.env["hr.leave"].create({
            "employee_id": self.employee.id,
            "holiday_status_id": self.exit_type.id,
            "request_unit_hours": True,
            "request_date_from": self.first,
            "request_date_to": self.first,
            "request_hour_from": "10",
            "request_hour_to": "12",
            "insea_exit_reason": "personal",
        })
        adjacent.action_confirm()

        first.write({"state": "validate"})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            approved_overlap = self._exit(self.first)

    def test_cross_team_manager_cannot_see_or_approve(self):
        manager_a = self._insea_user(
            "insea-manager-a",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        manager_b = self._insea_user(
            "insea-manager-b",
            "base.group_user,hr_holidays.group_hr_holidays_responsible",
        )
        employee_a = self.env["hr.employee"].create({
            "name": "Employé équipe A",
            "user_id": self._insea_user("insea-employee-a").id,
        })
        employee_a.leave_manager_id = manager_a
        leave_a = self.env["hr.leave"].create({
            "employee_id": employee_a.id,
            "holiday_status_id": self.exit_type.id,
            "request_unit_hours": True,
            "request_date_from": self.first,
            "request_date_to": self.first,
            "request_hour_from": "8",
            "request_hour_to": "10",
            "insea_exit_reason": "personal",
        })
        leave_a.action_confirm()
        self.assertFalse(
            leave_a.with_user(manager_b).search([("id", "=", leave_a.id)])
        )
        with self.assertRaises(AccessError):
            leave_a.with_user(manager_b).action_approve()

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


PENDING_OR_APPROVED = ("confirm", "validate1", "validate")
FAMILY_DURATIONS = {"marriage": (4,), "birth": (3,), "bereavement": (2, 3)}


class HrLeave(models.Model):
    _inherit = "hr.leave"

    insea_policy = fields.Selection(related="holiday_status_id.insea_policy", store=True)
    insea_exit_reason = fields.Selection(
        [
            ("medical", "Consultation médicale"),
            ("administrative", "Démarche administrative"),
            ("personal", "Urgence personnelle"),
        ],
        string="Motif de sortie",
        copy=False,
    )
    insea_exit_hours = fields.Float(
        compute="_compute_insea_exit_hours", store=True, string="Heures de sortie"
    )
    insea_needs_attachment = fields.Boolean(
        compute="_compute_insea_needs_attachment", string="Justificatif obligatoire"
    )

    _sql_constraints = [
        (
            "insea_short_exit_window",
            "CHECK (insea_policy IS DISTINCT FROM 'short_exit' "
            "OR date_to - date_from <= INTERVAL '4 hours')",
            "Une autorisation de sortie ne peut pas dépasser quatre heures.",
        ),
    ]

    @api.depends("holiday_status_id")
    def _compute_state(self):
        super()._compute_state()
        for leave in self.filtered("insea_policy"):
            leave.state = "draft"

    @api.model_create_multi
    def create(self, vals_list):
        type_ids = [vals["holiday_status_id"] for vals in vals_list if vals.get("holiday_status_id")]
        managed_ids = set(self.env["hr.leave.type"].browse(type_ids).filtered("insea_policy").ids)
        normalized = [
            dict(vals, state="draft")
            if vals.get("holiday_status_id") in managed_ids
            else vals
            for vals in vals_list
        ]
        return super().create(normalized)

    @api.depends("insea_policy", "date_from", "date_to")
    def _compute_insea_exit_hours(self):
        for leave in self:
            leave.insea_exit_hours = (
                (leave.date_to - leave.date_from).total_seconds() / 3600
                if leave.insea_policy == "short_exit" and leave.date_from and leave.date_to
                else 0
            )

    @api.depends("insea_policy", "insea_exit_reason")
    def _compute_insea_needs_attachment(self):
        for leave in self:
            leave.insea_needs_attachment = (
                leave.insea_policy in (*FAMILY_DURATIONS, "sickness")
                or (leave.insea_policy == "short_exit" and leave.insea_exit_reason == "medical")
            )

    def write(self, vals):
        entering_workflow = self.filtered(
            lambda leave: leave.insea_policy and leave.state not in PENDING_OR_APPROVED
        ) if vals.get("state") in PENDING_OR_APPROVED else self.browse()
        result = super().write(vals)
        for leave in entering_workflow:
            if leave.insea_policy == "annual" and leave.number_of_days > 3:
                today = fields.Date.context_today(leave.with_context(tz=leave.tz))
                if leave.request_date_from < today + timedelta(days=7):
                    raise ValidationError(
                        _("Un congé payé de plus de trois jours doit être soumis au moins sept jours à l'avance.")
                    )
            leave._check_date()
        return result

    @api.constrains(
        "holiday_status_id", "employee_id", "employee_ids", "state", "active",
        "request_date_from", "request_date_to", "request_unit_hours",
        "request_hour_from", "request_hour_to", "insea_exit_reason",
    )
    def _check_insea_request(self):
        managed = self.filtered(
            lambda leave: leave.insea_policy and leave.active
            and leave.state in PENDING_OR_APPROVED
        )
        for leave in managed:
            if leave.holiday_type != "employee" or not leave.employee_id or len(leave.employee_ids) > 1:
                raise ValidationError(_("Une demande INSEA doit concerner un seul collaborateur."))
            if leave.insea_policy == "short_exit":
                if not leave.insea_exit_reason:
                    raise ValidationError(_("Choisis un motif avant de soumettre la demande."))
                if (
                    not leave.request_unit_hours or leave.insea_exit_hours <= 0
                    or leave.insea_exit_hours > 4
                    or leave.request_date_to != leave.request_date_from
                ):
                    raise ValidationError(_("Choisis une plage horaire de 4 heures maximum sur une seule journée."))
            durations = FAMILY_DURATIONS.get(leave.insea_policy)
            if durations and leave.number_of_days not in durations:
                raise ValidationError(
                    _("Durée autorisée pour ce congé, en jours travaillés : %s.")
                    % " ou ".join(map(str, durations))
                )

        managed.filtered(lambda leave: leave.insea_policy == "short_exit")._check_insea_exit_quota()

    def _check_insea_exit_quota(self):
        # Odoo utilise des transactions à snapshot. Une écriture sur la même
        # ligne oblige une soumission concurrente à recommencer sa transaction.
        for employee_id in sorted(self.employee_id.ids):
            self.env.cr.execute(
                "UPDATE hr_employee SET insea_leave_revision = "
                "NOT COALESCE(insea_leave_revision, FALSE) WHERE id = %s",
                [employee_id],
            )
        for leave in self:
            month_start = leave.request_date_from.replace(day=1)
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            [(count, total_hours)] = self.sudo()._read_group(
                [
                    ("employee_id", "=", leave.employee_id.id),
                    ("insea_policy", "=", "short_exit"),
                    ("state", "in", PENDING_OR_APPROVED),
                    ("active", "=", True),
                    ("request_date_from", ">=", month_start),
                    ("request_date_from", "<", next_month),
                ],
                aggregates=["__count", "insea_exit_hours:sum"],
            )
            if count > 3 or (total_hours or 0) > 8:
                raise ValidationError(_("Le mois est limité à trois autorisations et huit heures cumulées."))

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
    insea_refusal_reason = fields.Text(
        string="Motif de refus", copy=False, tracking=True
    )
    insea_final_approved = fields.Boolean(
        string="Approbation finale enregistrée",
        default=False,
        copy=False,
        readonly=True,
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

    @api.depends("state", "employee_id", "insea_policy")
    def _compute_can_approve(self):
        super()._compute_can_approve()
        if self.env.su:
            return
        for leave in self.filtered("insea_policy"):
            if leave.state == "confirm":
                leave.can_approve = (
                    bool(leave.employee_id.leave_manager_id)
                    and leave.employee_id.leave_manager_id == self.env.user
                )
            elif leave.state == "validate1":
                leave.can_approve = self.env.user.has_group(
                    "hr_holidays.group_hr_holidays_user"
                ) and leave.employee_id.leave_manager_id != self.env.user
            else:
                leave.can_approve = False

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
        if not self.env.su:
            workflow_fields = {
                "state", "first_approver_id", "second_approver_id",
                "meeting_id", "insea_refusal_reason", "active",
                "attachment_ids", "supported_attachment_ids",
                "message_main_attachment_id", "insea_final_approved",
            }
            submitted = self.filtered(
                lambda leave: leave.insea_policy and leave.state in PENDING_OR_APPROVED
            )
            if submitted and set(vals) - workflow_fields:
                raise AccessError(_("Une demande soumise ne peut plus être modifiée."))
            if submitted and "insea_refusal_reason" in vals:
                for leave in submitted:
                    is_manager = (
                        leave.employee_id.leave_manager_id == self.env.user
                    )
                    is_hr = self.env.user.has_group(
                        "hr_holidays.group_hr_holidays_user"
                    )
                    if not is_manager and not is_hr:
                        raise AccessError(
                            _("Seuls les approbateurs peuvent saisir un motif de refus.")
                        )

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
        "holiday_status_id", "employee_id", "state", "active",
        "request_date_from", "request_date_to", "request_unit_hours",
        "request_hour_from", "request_hour_to", "insea_exit_reason",
    )
    def _check_insea_request(self):
        managed = self.filtered(
            lambda leave: leave.insea_policy and leave.active
            and leave.state in PENDING_OR_APPROVED
        )
        for leave in managed:
            leave._check_insea_overlap()
            if leave.holiday_type != "employee" or not leave.employee_id:
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

        managed.employee_id._insea_serialize_requests()
        managed.filtered(lambda leave: leave.insea_policy == "short_exit")._check_insea_exit_quota()

    def _check_insea_exit_quota(self):
        for leave in self:
            month_start = leave.request_date_from.replace(day=1)
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            domain = [
                ("employee_id", "=", leave.employee_id.id),
                ("insea_policy", "=", "short_exit"),
                ("state", "in", PENDING_OR_APPROVED),
                ("active", "=", True),
                ("id", "!=", leave.id),
                ("request_date_from", ">=", month_start),
                ("request_date_from", "<", next_month),
            ]
            count = self.sudo().search_count(domain)
            [(total_hours,)] = self.sudo()._read_group(
                domain,
                aggregates=["insea_exit_hours:sum"],
            )
            proposed_count = count + 1
            proposed_hours = (total_hours or 0) + leave.insea_exit_hours
            if proposed_count > 3:
                raise ValidationError(_("Le mois est limité à trois autorisations de sortie."))
            if proposed_hours > 8:
                raise ValidationError(_("Le mois est limité à huit heures cumulées de sortie."))

    def _check_insea_overlap(self):
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return
        conflicting = self.sudo().search([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("active", "=", True),
            ("state", "in", PENDING_OR_APPROVED),
            ("date_from", "<", self.date_to),
            ("date_to", ">", self.date_from),
        ], limit=1)
        if conflicting:
            raise ValidationError(
                _("Cette demande chevauche une autre demande INSEA ou congé en attente ou approuvé.")
            )

    def _check_insea_submitter(self):
        if self.env.su:
            return
        for leave in self:
            if leave.employee_id.user_id and leave.employee_id.user_id != self.env.user:
                raise AccessError(_("Seul le collaborateur concerné peut soumettre sa demande."))

    def _check_insea_manager(self):
        if self.env.su:
            return
        for leave in self:
            manager = leave.employee_id.leave_manager_id
            if not manager or manager != self.env.user:
                raise AccessError(_("Seul le manager direct du collaborateur peut effectuer cette approbation."))

    def _check_insea_hr(self):
        if self.env.su:
            return
        if not self.env.user.has_group("hr_holidays.group_hr_holidays_user"):
            raise AccessError(_("Seul le Responsable RH peut effectuer cette approbation finale."))
        for leave in self:
            if leave.employee_id.leave_manager_id == self.env.user:
                raise ValidationError(
                    _("Le manager ne peut pas effectuer les deux niveaux d'approbation.")
                )

    def _check_insea_support_document(self):
        for leave in self:
            if not leave.insea_needs_attachment:
                continue
            documents = leave.supported_attachment_ids
            valid = any(
                (attachment.mimetype or "").startswith("image/")
                or (attachment.mimetype or "").lower() == "application/pdf"
                or (attachment.name or "").lower().endswith(".pdf")
                or (attachment.name or "").lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
                for attachment in documents
            )
            if not valid:
                raise ValidationError(
                    _("Un justificatif PDF ou image est obligatoire avant l'approbation finale.")
                )

    def _get_employees_from_holiday_type(self):
        employees = self.env["hr.employee"]
        for leave in self:
            if leave.holiday_type == "employee" and leave.employee_id:
                employees |= leave.employee_id
            else:
                employees |= super(HrLeave, leave)._get_employees_from_holiday_type()
        return employees

    def action_confirm(self):
        self._check_insea_submitter()
        for leave in self:
            if leave.state != "draft":
                raise ValidationError(_("La demande doit être en brouillon pour être soumise."))
            if leave.insea_policy == "short_exit" and not leave.insea_exit_reason:
                raise ValidationError(_("Choisis un motif avant de soumettre la demande."))
            leave._check_insea_request()
        return super().action_confirm()

    def action_approve(self, check_state=True):
        for leave in self:
            if leave.insea_policy:
                if leave.state != "confirm":
                    raise ValidationError(_("La demande doit être en attente d'approbation manager."))
                leave._check_insea_manager()
        return super().action_approve(check_state=check_state)

    def action_validate(self):
        for leave in self:
            if leave.insea_policy:
                if leave.state == "confirm" and leave.insea_policy == "short_exit":
                    leave._check_insea_manager()
                elif leave.state == "validate1":
                    leave._check_insea_hr()
                else:
                    raise ValidationError(_("Cette demande n’est pas à une étape finale d’approbation valide."))
                leave._check_insea_support_document()
                if leave.insea_final_approved:
                    raise ValidationError(_("Cette demande a déjà reçu son approbation finale."))
        result = super().action_validate()
        self.filtered("insea_policy").write({"insea_final_approved": True})
        return result

    def action_refuse(self):
        for leave in self:
            if leave.insea_policy:
                if leave.state not in ("confirm", "validate1"):
                    raise ValidationError(_("Le refus ne peut être effectué qu'à un niveau d'approbation."))
                if not leave.insea_refusal_reason or not leave.insea_refusal_reason.strip():
                    raise ValidationError(_("Un motif de refus est obligatoire."))
                if leave.state == "confirm":
                    leave._check_insea_manager()
                else:
                    leave._check_insea_hr()
        result = super().action_refuse()
        for leave in self.filtered("insea_policy"):
            if leave.employee_id.user_id:
                leave.message_post(
                    partner_ids=[leave.employee_id.user_id.partner_id.id],
                    body=_(
                        "Votre demande %(leave)s a été refusée. Motif : %(reason)s",
                        leave=leave.holiday_status_id.display_name,
                        reason=leave.insea_refusal_reason,
                    ),
                    subtype_xmlid="mail.mt_comment",
                )
        return result

    def action_draft(self):
        if not self.env.su:
            submitted = self.filtered(
                lambda leave: leave.insea_policy and leave.state in PENDING_OR_APPROVED
            )
            if submitted:
                raise AccessError(_("Une demande soumise ne peut pas être remise en brouillon."))
        return super().action_draft()

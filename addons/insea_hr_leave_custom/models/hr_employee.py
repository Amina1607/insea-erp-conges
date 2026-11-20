from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    insea_leave_revision = fields.Boolean(
        groups="base.group_system",
        readonly=True,
        copy=False,
        help="Sérialise les contrôles de quota pour les demandes simultanées.",
    )

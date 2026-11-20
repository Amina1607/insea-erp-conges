from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    insea_policy = fields.Selection(
        [
            ("short_exit", "Autorisation de sortie"),
            ("annual", "Congé payé annuel"),
            ("marriage", "Mariage"),
            ("birth", "Naissance"),
            ("bereavement", "Décès"),
            ("sickness", "Maladie"),
        ],
        string="Règle INSEA",
        readonly=True,
        copy=False,
    )

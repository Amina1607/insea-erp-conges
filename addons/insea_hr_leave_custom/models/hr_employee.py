from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    insea_leave_revision = fields.Boolean(
        groups="base.group_system",
        readonly=True,
        copy=False,
        help="Sérialise les contrôles métier pour les demandes simultanées.",
    )

    def _insea_serialize_requests(self):
        # Une écriture concurrente sur la même ligne force le deuxième
        # traitement à reprendre avec une vue à jour des demandes existantes.
        for employee_id in sorted(self.ids):
            self.env.cr.execute(
                "UPDATE hr_employee SET insea_leave_revision = "
                "NOT COALESCE(insea_leave_revision, FALSE) WHERE id = %s",
                [employee_id],
            )
        self.invalidate_recordset(["insea_leave_revision"], flush=False)

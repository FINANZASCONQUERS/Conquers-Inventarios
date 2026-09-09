from odoo import api, fields, models


class OperacionesConductor(models.Model):
    """Directorio de conductores y su vehiculo habitual.

    Existe para que al digitar la placa en la sabana de cargue se autocompleten
    conductor, cedula, celular, tanque y transportadora sin volver a teclearlos.
    """
    _name = 'operaciones.conductor'
    _description = 'Conductor y vehiculo'
    _inherit = ['mail.thread']
    _order = 'nombre'
    _rec_name = 'nombre'

    nombre = fields.Char(required=True, tracking=True)
    cedula = fields.Char(string='Cedula', required=True, index=True, tracking=True)
    celular = fields.Char(tracking=True)

    placa = fields.Char(string='Placa cabezote', index=True, tracking=True)
    tanque = fields.Char(string='Tanque habitual', tracking=True)
    transportadora_id = fields.Many2one(
        'res.partner', string='Empresa transportadora',
        domain="[('is_company', '=', True)]", tracking=True)

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('uq_cedula', 'unique(cedula)',
         'Ya existe un conductor con esa cedula.'),
    ]

    @api.depends('nombre', 'placa')
    def _compute_display_name(self):
        for reg in self:
            reg.display_name = '%s - %s' % (reg.placa or 's/placa', reg.nombre or '')

    @api.model
    def buscar_por_placa(self, placa):
        """Devuelve los datos para autocompletar una fila de cargue."""
        if not placa:
            return {}
        conductor = self.search([('placa', '=ilike', placa.strip())], limit=1)
        if not conductor:
            return {}
        return {
            'conductor_id': conductor.id,
            'cedula_conductor': conductor.cedula,
            'celular_conductor': conductor.celular,
            'tanque': conductor.tanque,
            'empresa_transportadora_id': conductor.transportadora_id.id,
        }

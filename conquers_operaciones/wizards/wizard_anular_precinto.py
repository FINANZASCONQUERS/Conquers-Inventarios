from odoo import _, api, fields, models


class AnularPrecintoWizard(models.TransientModel):
    """Sacar un sello de circulacion, pidiendo siempre el motivo."""
    _name = 'operaciones.anular.precinto.wizard'
    _description = 'Anular precinto'

    precinto_id = fields.Many2one('operaciones.precinto', required=True,
                                  readonly=True)
    codigo = fields.Char(related='precinto_id.codigo', readonly=True)
    cargue_id = fields.Many2one(related='precinto_id.cargue_id', readonly=True)

    tipo = fields.Selection([
        ('ROTO', 'Se rompio al colocarlo'),
        ('AJUSTE', 'Ajuste de inventario'),
    ], required=True, default='ROTO')
    motivo = fields.Char(required=True)
    reemplazar = fields.Boolean(
        string='Tomar un reemplazo del stock', default=True,
        help='Si el sello estaba puesto en un viaje, toma el siguiente '
             'disponible y lo pone en su lugar.')

    aviso = fields.Char(compute='_compute_aviso')

    @api.depends('precinto_id', 'tipo', 'reemplazar')
    def _compute_aviso(self):
        for wiz in self:
            if wiz.tipo == 'AJUSTE':
                wiz.aviso = _('El ajuste no cuenta como merma en el resumen.')
            elif wiz.reemplazar and wiz.cargue_id:
                wiz.aviso = _('Se tomara un sello del stock para el viaje %s.') % (
                    wiz.cargue_id.placa or wiz.cargue_id.id)
            else:
                wiz.aviso = False

    @api.onchange('tipo')
    def _onchange_tipo(self):
        # Un rollo viejo que ya no esta en bodega no se reemplaza en un viaje.
        if self.tipo == 'AJUSTE':
            self.reemplazar = False

    def action_anular(self):
        self.ensure_one()
        self.precinto_id.action_anular(motivo=self.motivo, tipo=self.tipo,
                                       reemplazar=self.reemplazar)
        return {'type': 'ir.actions.act_window_close'}

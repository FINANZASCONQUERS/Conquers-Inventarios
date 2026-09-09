from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OperacionesProgramacionBase(models.Model):
    """El pedido tal como lo pide el cliente, antes de tener camion asignado.

    Comercial registra aqui que producto, cuanto y para donde. Cuando hay
    transporte, el pedido pasa a la sabana de cargue y queda enlazado para
    poder comparar lo pedido contra lo despachado.
    """
    _name = 'operaciones.programacion.base'
    _description = 'Pedido (programacion base)'
    _inherit = ['mail.thread']
    _order = 'fecha_cargue desc, id desc'
    _rec_name = 'display_name'

    fecha_cargue = fields.Date(string='Fecha estimada', required=True,
                               default=fields.Date.context_today, index=True,
                               tracking=True)
    fecha_cargue_confirmada = fields.Date(string='Fecha confirmada', tracking=True)

    producto_id = fields.Many2one('product.product', string='Producto',
                                  required=True, tracking=True)
    cliente_id = fields.Many2one('res.partner', string='Cliente', required=True,
                                 index=True, tracking=True)
    destino = fields.Char(tracking=True)
    calidad = fields.Char(tracking=True)
    galones = fields.Float(tracking=True)
    barriles = fields.Float(compute='_compute_barriles', store=True,
                            digits=(16, 2))

    cargue_id = fields.Many2one('operaciones.cargue', string='Viaje',
                                readonly=True, copy=False, index=True)
    estado = fields.Selection([
        ('PENDIENTE', 'Pendiente'),
        ('PROGRAMADO', 'Programado'),
        ('DESPACHADO', 'Despachado'),
    ], required=True, default='PENDIENTE', index=True, tracking=True)

    observaciones = fields.Text()

    @api.depends('galones')
    def _compute_barriles(self):
        from .programacion_cargue import GALONES_POR_BARRIL
        for pedido in self:
            pedido.barriles = round((pedido.galones or 0.0) / GALONES_POR_BARRIL, 2)

    @api.depends('cliente_id', 'producto_id', 'fecha_cargue')
    def _compute_display_name(self):
        for pedido in self:
            pedido.display_name = '%s - %s (%s)' % (
                pedido.cliente_id.name or '?',
                pedido.producto_id.name or '?',
                pedido.fecha_cargue or '')

    def action_enviar_a_programacion(self):
        """Crea la fila en la sabana de cargue con lo que ya se sabe del pedido."""
        cargues = self.env['operaciones.cargue']
        for pedido in self:
            if pedido.cargue_id:
                raise UserError(_(
                    'El pedido de %s ya esta en la sabana de cargue.'
                ) % pedido.cliente_id.name)
            cargue = cargues.create({
                'fecha_programacion': (pedido.fecha_cargue_confirmada
                                       or pedido.fecha_cargue),
                'cliente_id': pedido.cliente_id.id,
                'producto_id': pedido.producto_id.id,
                'destino': pedido.destino,
                'galones': pedido.galones,
                'programacion_base_id': pedido.id,
            })
            pedido.write({'cargue_id': cargue.id, 'estado': 'PROGRAMADO'})
            pedido.message_post(body=_('Enviado a programacion de cargue.'))
            cargues |= cargue

        return {
            'type': 'ir.actions.act_window',
            'name': _('Programacion de cargue'),
            'res_model': 'operaciones.cargue',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', cargues.ids)],
        }

    def action_ver_cargue(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'operaciones.cargue',
            'res_id': self.cargue_id.id,
            'view_mode': 'form',
        }

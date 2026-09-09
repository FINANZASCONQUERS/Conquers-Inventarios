from odoo import _, api, fields, models


class AsignarPrecintosWizard(models.TransientModel):
    """Asignacion con cantidad distinta a la de siempre.

    El boton rapido de la sabana toma 5. Este asistente es para el viaje que
    lleva mas o menos sellos, y para confirmar cuando la fila ya tenia.
    """
    _name = 'operaciones.asignar.precintos.wizard'
    _description = 'Asignar precintos a un viaje'

    cargue_id = fields.Many2one('operaciones.cargue', required=True,
                                readonly=True)
    cantidad = fields.Integer(required=True, default=5)
    forzar = fields.Boolean(
        string='Agregar de todas formas',
        help='Marca esto solo si el viaje necesita sellos adicionales sobre los '
             'que ya tiene. Si lo que quieres es corregir, libera primero.')

    ya_asignados = fields.Integer(compute='_compute_contexto')
    disponibles = fields.Integer(compute='_compute_contexto')
    aviso_stock = fields.Char(compute='_compute_contexto')

    @api.depends('cargue_id', 'cantidad')
    def _compute_contexto(self):
        Precinto = self.env['operaciones.precinto']
        for wiz in self:
            wiz.ya_asignados = len(wiz.cargue_id.precinto_ids.filtered(
                lambda p: p.estado == 'USADO'))
            wiz.disponibles = Precinto.search_count([('estado', '=', 'DISPONIBLE')])
            if wiz.disponibles < wiz.cantidad:
                wiz.aviso_stock = _(
                    'Solo hay %s precintos disponibles. Registra un lote nuevo.'
                ) % wiz.disponibles
            elif wiz.disponibles < Precinto._stock_minimo():
                wiz.aviso_stock = _(
                    'Quedan %s precintos en bodega. Conviene pedir un lote nuevo.'
                ) % wiz.disponibles
            else:
                wiz.aviso_stock = False

    def action_asignar(self):
        self.ensure_one()
        self.cargue_id.action_asignar_precintos(cantidad=self.cantidad,
                                                forzar=self.forzar)
        return {'type': 'ir.actions.act_window_close'}

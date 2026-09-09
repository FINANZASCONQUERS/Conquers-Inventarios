from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Los sellos se numeran a 6 digitos: 4346 se escribe 004346.
PRECINTOS_DIGITOS = 6
# Por debajo de este stock la vista avisa que hay que pedir lote nuevo.
PRECINTOS_STOCK_MINIMO = 100


def formatear_codigo(numero, digitos=PRECINTOS_DIGITOS):
    """004346 a partir de 4346. Los valores no numericos se dejan tal cual."""
    try:
        return str(int(numero)).zfill(int(digitos or PRECINTOS_DIGITOS))
    except (TypeError, ValueError):
        return str(numero or '')


class OperacionesLotePrecintos(models.Model):
    """Paquete de precintos que entra a bodega con numeracion consecutiva."""
    _name = 'operaciones.lote.precintos'
    _description = 'Lote de precintos'
    _inherit = ['mail.thread']
    _order = 'fecha_ingreso desc, id desc'

    name = fields.Char(string='Lote', required=True, copy=False,
                       default=lambda s: _('Nuevo'))
    rango_inicial = fields.Integer(required=True, tracking=True)
    rango_final = fields.Integer(required=True, tracking=True)
    numero_digitos = fields.Integer(default=PRECINTOS_DIGITOS, required=True)

    color = fields.Char(default='Verde', tracking=True)
    proveedor_id = fields.Many2one('res.partner', string='Proveedor', tracking=True)
    documento_remision = fields.Char(string='Documento de remision', tracking=True)
    fecha_ingreso = fields.Date(default=fields.Date.context_today, required=True,
                                tracking=True)

    precinto_ids = fields.One2many('operaciones.precinto', 'lote_id',
                                   string='Sellos')
    total_precintos = fields.Integer(compute='_compute_totales', store=True)
    disponibles = fields.Integer(compute='_compute_totales', store=True)
    usados = fields.Integer(compute='_compute_totales', store=True)
    anulados = fields.Integer(compute='_compute_totales', store=True)

    observaciones = fields.Text()
    sellos_generados = fields.Boolean(default=False, copy=False, readonly=True)
    active = fields.Boolean(default=True)

    @api.depends('precinto_ids', 'precinto_ids.estado')
    def _compute_totales(self):
        for lote in self:
            sellos = lote.precinto_ids
            lote.total_precintos = len(sellos)
            lote.disponibles = len(sellos.filtered(lambda p: p.estado == 'DISPONIBLE'))
            lote.usados = len(sellos.filtered(lambda p: p.estado == 'USADO'))
            lote.anulados = len(sellos.filtered(lambda p: p.estado == 'ANULADO'))

    @api.constrains('rango_inicial', 'rango_final')
    def _check_rango(self):
        for lote in self:
            if lote.rango_final < lote.rango_inicial:
                raise ValidationError(_(
                    'El rango final (%s) no puede ser menor que el inicial (%s).'
                ) % (lote.rango_final, lote.rango_inicial))
            if lote.rango_final - lote.rango_inicial > 100000:
                raise ValidationError(_(
                    'El rango tiene %s sellos. Revisa los numeros: un lote de mas '
                    'de 100.000 casi siempre es un error de digitacion.'
                ) % (lote.rango_final - lote.rango_inicial + 1))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'operaciones.lote.precintos') or _('Nuevo')
        return super().create(vals_list)

    def action_generar_sellos(self):
        """Crea un registro por cada numero del rango, en estado DISPONIBLE.

        Se salta los numeros que ya existan como DISPONIBLE en otro lote: el
        indice unico parcial de operaciones.precinto los rechazaria de todas
        formas y asi el mensaje es claro en vez de un error de base de datos.
        """
        Precinto = self.env['operaciones.precinto']
        for lote in self:
            if lote.sellos_generados:
                raise UserError(_(
                    'El lote %s ya tiene sus sellos generados. Para corregir el '
                    'rango, crea un lote nuevo.') % lote.name)

            numeros = list(range(lote.rango_inicial, lote.rango_final + 1))
            ya_disponibles = set(Precinto.search([
                ('numero', 'in', numeros), ('estado', '=', 'DISPONIBLE'),
            ]).mapped('numero'))

            nuevos = [{
                'lote_id': lote.id,
                'numero': n,
                'codigo': formatear_codigo(n, lote.numero_digitos),
                'estado': 'DISPONIBLE',
            } for n in numeros if n not in ya_disponibles]

            if nuevos:
                Precinto.create(nuevos)
            lote.sellos_generados = True

            mensaje = _('Se generaron %s sellos.') % len(nuevos)
            if ya_disponibles:
                mensaje += _(' Se omitieron %s que ya estaban disponibles en otro '
                             'lote.') % len(ya_disponibles)
            lote.message_post(body=mensaje)
        return True

    def action_ver_sellos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sellos del lote %s') % self.name,
            'res_model': 'operaciones.precinto',
            'view_mode': 'tree,form',
            'domain': [('lote_id', '=', self.id)],
            'context': {'default_lote_id': self.id},
        }

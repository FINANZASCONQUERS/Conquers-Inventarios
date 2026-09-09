from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Saltarse 1 o 2 numeros es normal: son sellos que se rompen al colocarlos.
# A partir de este salto la vista lo marca para que alguien lo revise.
PRECINTOS_SALTO_TOLERADO = 3


class OperacionesPrecinto(models.Model):
    """Un precinto individual y todo lo que se sabe de donde termino.

    El numero vive como registro propio, no como texto en la fila de cargue:
    nace DISPONIBLE al entrar el lote a bodega y solo puede morir USADO o
    ANULADO.
    """
    _name = 'operaciones.precinto'
    _description = 'Precinto de seguridad'
    _order = 'numero'
    _rec_name = 'codigo'

    lote_id = fields.Many2one('operaciones.lote.precintos', string='Lote',
                              ondelete='restrict', index=True)
    numero = fields.Integer(required=True, index=True)
    codigo = fields.Char(required=True, index=True,
                         help='El numero formateado a 6 digitos: 004346.')
    estado = fields.Selection([
        ('DISPONIBLE', 'Disponible'),
        ('USADO', 'Usado'),
        ('ANULADO', 'Anulado'),
    ], required=True, default='DISPONIBLE', index=True)

    # --- Trazabilidad: a que viaje se fue el sello -------------------------
    cargue_id = fields.Many2one('operaciones.cargue', string='Viaje',
                                ondelete='set null', index=True)
    placa = fields.Char()
    numero_guia = fields.Char(string='Numero de guia')
    cliente_id = fields.Many2one('res.partner', string='Cliente')
    producto_id = fields.Many2one('product.product', string='Producto')
    conductor = fields.Char()
    fecha_uso = fields.Date(index=True)
    usuario_uso_id = fields.Many2one('res.users', string='Asignado por')

    # --- Anulacion: el sello que se rompe al cerrar la valvula -------------
    motivo_anulacion = fields.Char()
    tipo_anulacion = fields.Selection([
        ('ROTO', 'Roto al colocar'),
        ('AJUSTE', 'Ajuste de inventario'),
    ], help='El ajuste saca de circulacion rollos viejos que ya no estan en '
            'bodega. Va a ANULADO igual que un sello roto, pero no es merma y '
            'se separa en el resumen.')
    fecha_anulacion = fields.Datetime()
    usuario_anulacion_id = fields.Many2one('res.users', string='Anulado por')
    precinto_reemplazo_id = fields.Many2one(
        'operaciones.precinto', string='Reemplazado por',
        help='Sello que entro al viaje en lugar de este cuando se anulo.')

    # --- Importacion del historico digitado a mano -------------------------
    origen = fields.Selection([
        ('INVENTARIO', 'Inventario'),
        ('HISTORICO', 'Historico importado'),
    ], default='INVENTARIO', required=True)
    texto_original = fields.Char(
        help='Como venia escrito en la columna vieja antes de migrar.')
    requiere_revision = fields.Boolean(index=True)
    nota_revision = fields.Char()

    def init(self):
        """Un numero no puede estar DISPONIBLE dos veces, pero si puede
        repetirse en USADO/ANULADO: el historico trae numeros duplicados por
        errores de digitacion que se conservan a proposito para auditoria.

        _sql_constraints no sabe expresar un indice parcial, por eso va aqui.
        """
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
              operaciones_precinto_disponible_uniq
            ON operaciones_precinto (numero)
            WHERE estado = 'DISPONIBLE'
        """)

    # ------------------------------------------------------------------
    #  Toma de consecutivos
    # ------------------------------------------------------------------
    @api.model
    def _tomar_disponibles(self, cantidad):
        """Bloquea y devuelve los siguientes N sellos disponibles.

        SKIP LOCKED evita que dos operadoras asignando a la vez se lleven el
        mismo consecutivo: la segunda salta las filas que la primera ya tiene
        tomadas en lugar de esperar o de recibir el mismo numero.

        El ORM no expone FOR UPDATE SKIP LOCKED, de ahi el SQL directo.
        """
        self.env.cr.execute("""
            SELECT id FROM operaciones_precinto
            WHERE estado = 'DISPONIBLE'
            ORDER BY numero ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        """, (cantidad,))
        ids = [fila[0] for fila in self.env.cr.fetchall()]
        return self.browse(ids)

    def marcar_usado(self, cargue):
        """Copia al sello los datos del viaje al que se va."""
        for precinto in self:
            precinto.write({
                'estado': 'USADO',
                'cargue_id': cargue.id,
                'placa': cargue.placa,
                'numero_guia': cargue.numero_guia,
                'cliente_id': cargue.cliente_id.id,
                'producto_id': cargue.producto_id.id,
                'conductor': cargue.conductor_id.nombre,
                'fecha_uso': (cargue.fecha_despacho or cargue.fecha_programacion
                              or fields.Date.context_today(self)),
                'usuario_uso_id': self.env.user.id,
            })

    def liberar(self):
        """Devuelve los sellos al stock y borra la trazabilidad del viaje."""
        return self.write({
            'estado': 'DISPONIBLE',
            'cargue_id': False,
            'placa': False,
            'numero_guia': False,
            'cliente_id': False,
            'producto_id': False,
            'conductor': False,
            'fecha_uso': False,
            'usuario_uso_id': False,
        })

    # ------------------------------------------------------------------
    #  Anulacion y reactivacion
    # ------------------------------------------------------------------
    def action_anular(self, motivo=None, tipo='ROTO', reemplazar=True):
        """Saca el sello de circulacion.

        Si estaba puesto en un viaje y `reemplazar` sigue activo, toma
        automaticamente el siguiente disponible y lo pone en su lugar: es lo
        que pasa en planta cuando un sello se rompe al colocarlo.
        """
        self.ensure_one()
        if self.estado == 'ANULADO':
            raise UserError(_('El precinto %s ya esta anulado.') % self.codigo)
        motivo = (motivo or '').strip()
        if not motivo:
            raise UserError(_('Debes indicar el motivo de la anulacion.'))

        cargue = self.cargue_id
        if cargue:
            cargue._verificar_candado_refineria({'precinto_ids': True})

        reemplazo = self.env['operaciones.precinto']
        if reemplazar and cargue:
            reemplazo = self._tomar_disponibles(1)
            if not reemplazo:
                raise UserError(_(
                    'No hay sellos disponibles para reemplazar el %s. '
                    'Registra un lote nuevo o anula sin reemplazo.') % self.codigo)
            reemplazo.marcar_usado(cargue)

        self.write({
            'estado': 'ANULADO',
            'motivo_anulacion': motivo,
            'tipo_anulacion': tipo,
            'fecha_anulacion': fields.Datetime.now(),
            'usuario_anulacion_id': self.env.user.id,
            'precinto_reemplazo_id': reemplazo.id if reemplazo else False,
        })

        if cargue:
            cargue._recalcular_precintos()
            cuerpo = _('Precinto %s anulado: %s.') % (self.codigo, motivo)
            if reemplazo:
                cuerpo += _(' Reemplazado por %s.') % reemplazo.codigo
            cargue.message_post(body=cuerpo)
        return True

    def action_reactivar(self):
        """Devuelve un sello anulado por error al stock."""
        for precinto in self:
            if precinto.estado != 'ANULADO':
                raise UserError(_(
                    'Solo se reactivan sellos anulados. El %s esta %s.'
                ) % (precinto.codigo, precinto.estado))
            duplicado = self.search([
                ('numero', '=', precinto.numero),
                ('estado', '=', 'DISPONIBLE'),
                ('id', '!=', precinto.id),
            ], limit=1)
            if duplicado:
                raise UserError(_(
                    'No se puede reactivar el %s: ese numero ya esta disponible '
                    'en el lote %s.') % (precinto.codigo,
                                         duplicado.lote_id.name or '-'))
            precinto.write({
                'estado': 'DISPONIBLE',
                'motivo_anulacion': False,
                'tipo_anulacion': False,
                'fecha_anulacion': False,
                'usuario_anulacion_id': False,
                'precinto_reemplazo_id': False,
                'cargue_id': False,
                'placa': False,
                'numero_guia': False,
                'cliente_id': False,
                'producto_id': False,
                'conductor': False,
                'fecha_uso': False,
                'usuario_uso_id': False,
            })
        return True

    def action_abrir_anular(self):
        """Abre el asistente que pide el motivo."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Anular precinto %s') % self.codigo,
            'res_model': 'operaciones.anular.precinto.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_precinto_id': self.id},
        }

    # ------------------------------------------------------------------
    #  Resumen de stock
    # ------------------------------------------------------------------
    @api.model
    def resumen(self):
        """Conteos para el tablero. El ajuste se separa porque no es merma."""
        agrupado = self.read_group([], ['estado'], ['estado'], lazy=False)
        conteos = {g['estado']: g['__count'] for g in agrupado}
        ajustes = self.search_count([('tipo_anulacion', '=', 'AJUSTE')])
        disponibles = conteos.get('DISPONIBLE', 0)
        return {
            'disponibles': disponibles,
            'usados': conteos.get('USADO', 0),
            'anulados': conteos.get('ANULADO', 0),
            'merma': conteos.get('ANULADO', 0) - ajustes,
            'ajustes': ajustes,
            'stock_bajo': disponibles < self._stock_minimo(),
        }

    @api.model
    def _stock_minimo(self):
        from .lote_precintos import PRECINTOS_STOCK_MINIMO
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'operaciones.precintos_stock_minimo', PRECINTOS_STOCK_MINIMO))

    @api.model
    def detectar_saltos(self, cargue_id):
        """Avisa si entre los sellos de un viaje hay un hueco sospechoso.

        Saltarse uno o dos numeros es normal. A partir de PRECINTOS_SALTO_
        TOLERADO conviene que alguien mire que paso con los del medio.
        """
        sellos = self.search([('cargue_id', '=', cargue_id)], order='numero')
        numeros = sellos.mapped('numero')
        saltos = []
        for anterior, siguiente in zip(numeros, numeros[1:]):
            if siguiente - anterior > PRECINTOS_SALTO_TOLERADO:
                saltos.append((anterior, siguiente))
        return saltos

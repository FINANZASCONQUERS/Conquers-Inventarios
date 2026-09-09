import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Un barril son 42 galones.
GALONES_POR_BARRIL = 42.0

# Minutos que tiene refineria para corregir despues de completar el viaje.
CANDADO_MINUTOS = 30

# Campos cuyo llenado completo arranca el reloj del candado.
CAMPOS_REFINERIA = ('galones', 'temperatura', 'api_obs', 'api_corregido')

# Cantidad de sellos que lleva un viaje normalmente, y tope de seguridad.
PRECINTOS_CANTIDAD_DEFECTO = 5
PRECINTOS_CANTIDAD_MAXIMA = 12

# Serie oficial de la guia fisica: 303400000 + folio de 4 digitos.
GUIA_FISICA_SERIE = '303400000'
GUIA_FISICA_FOLIO_MIN = 100
GUIA_FISICA_FOLIO_MAX = 1999
GUIA_FISICA_FOLIO_INICIAL = 601

# Que campos puede editar cada area. Es la unica fuente de verdad del permiso
# por campo: ir.model.access.csv solo sabe de modelos, y groups= en la vista es
# cosmetico porque se salta por RPC.
CAMPOS_POR_GRUPO = {
    'conquers_operaciones.group_logistica': {
        'factura', 'fecha_programacion', 'empresa_transportadora_id', 'placa',
        'tanque', 'conductor_id', 'cedula_conductor', 'celular_conductor',
        'hora_llegada_estimada', 'producto_id',
    },
    'conquers_operaciones.group_comercial': {
        'cliente_id', 'destino',
    },
    'conquers_operaciones.group_refineria': {
        'estado', 'galones', 'temperatura', 'api_obs', 'api_corregido',
        'fecha_despacho', 'precinto_ids',
    },
    'conquers_operaciones.group_guias': {
        'numero_guia', 'tipo_guia', 'imagen_guia', 'nombre_imagen_guia',
    },
    'conquers_operaciones.group_facturacion': {
        'factura_sicom', 'fecha_factura', 'mes_facturado', 'codigo_transporte',
    },
}

# Campos tecnicos que cualquiera puede tocar sin permiso especial.
CAMPOS_LIBRES = {
    'message_follower_ids', 'message_ids', 'activity_ids', 'observaciones',
    'programacion_base_id', 'refineria_completado_en',
}


class OperacionesCargue(models.Model):
    """La sabana de operaciones: un viaje por fila.

    Cuatro areas escriben sobre la misma fila el mismo dia. Logistica pone el
    transporte, comercial el cliente, refineria los aforos y facturacion el
    SICOM. De ahi que el permiso sea por campo y no por registro.
    """
    _name = 'operaciones.cargue'
    _description = 'Programacion de cargue'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha_programacion desc, id desc'

    # ------------------------------------------------------------------
    #  Logistica
    # ------------------------------------------------------------------
    factura = fields.Char(string='Factura', tracking=True)
    fecha_programacion = fields.Date(
        required=True, default=fields.Date.context_today, index=True, tracking=True)
    empresa_transportadora_id = fields.Many2one(
        'res.partner', string='Transportadora',
        domain="[('is_company', '=', True)]", tracking=True)
    placa = fields.Char(index=True, tracking=True)
    tanque = fields.Char(tracking=True)
    conductor_id = fields.Many2one('operaciones.conductor', string='Conductor',
                                   tracking=True)
    cedula_conductor = fields.Char(string='Cedula')
    celular_conductor = fields.Char(string='Celular')
    # Odoo no tiene campo Time: la hora va como float con widget float_time.
    hora_llegada_estimada = fields.Float(string='Hora estimada')
    producto_id = fields.Many2one('product.product', string='Producto a cargar',
                                  tracking=True)

    # ------------------------------------------------------------------
    #  Comercial
    # ------------------------------------------------------------------
    cliente_id = fields.Many2one('res.partner', string='Cliente', index=True,
                                 tracking=True)
    destino = fields.Char(tracking=True)

    # ------------------------------------------------------------------
    #  Refineria
    # ------------------------------------------------------------------
    # CANCELADO no aparece en el sistema actual. Antes de agregarlo hay que
    # correr SELECT DISTINCT estado FROM programacion_cargue en produccion.
    estado = fields.Selection([
        ('PROGRAMADO', 'Programado'),
        ('CARGANDO', 'Cargando'),
        ('CARGADO', 'Cargado'),
        ('DESPACHADO', 'Despachado'),
    ], required=True, default='PROGRAMADO', index=True, tracking=True)

    galones = fields.Float(tracking=True)
    barriles = fields.Float(compute='_compute_barriles', store=True,
                            digits=(16, 2), tracking=True)
    temperatura = fields.Float(tracking=True)
    api_obs = fields.Float(string='API observado', tracking=True)
    api_corregido = fields.Float(string='API corregido', tracking=True)
    fecha_despacho = fields.Date(index=True, tracking=True)

    refineria_completado_en = fields.Datetime(readonly=True, copy=False)
    refineria_bloqueado = fields.Boolean(compute='_compute_refineria_bloqueado')

    # ------------------------------------------------------------------
    #  Precintos
    # ------------------------------------------------------------------
    precinto_ids = fields.One2many('operaciones.precinto', 'cargue_id',
                                   string='Precintos')
    precintos_texto = fields.Char(
        string='Precintos', compute='_compute_precintos_texto', store=True,
        help='Los codigos separados por guion, como se venian escribiendo: '
             '004346-004347-004348-004349-004350.')

    # ------------------------------------------------------------------
    #  Guia
    # ------------------------------------------------------------------
    numero_guia = fields.Char(string='Numero de guia', index=True, tracking=True)
    tipo_guia = fields.Selection([
        ('FISICA', 'Fisica'),
        ('DIGITAL', 'Digital'),
    ], default='FISICA', tracking=True)
    imagen_guia = fields.Binary(string='Guia escaneada', attachment=True)
    nombre_imagen_guia = fields.Char()

    # ------------------------------------------------------------------
    #  Facturacion
    # ------------------------------------------------------------------
    factura_sicom = fields.Char(string='Factura SICOM', tracking=True)
    fecha_factura = fields.Date(tracking=True)
    mes_facturado = fields.Char()
    codigo_transporte = fields.Char()

    # ------------------------------------------------------------------
    #  Enlaces y permisos calculados
    # ------------------------------------------------------------------
    programacion_base_id = fields.Many2one(
        'operaciones.programacion.base', string='Pedido de origen',
        ondelete='set null', index=True)
    observaciones = fields.Text()

    puede_editar_logistica = fields.Boolean(compute='_compute_permisos')
    puede_editar_comercial = fields.Boolean(compute='_compute_permisos')
    puede_editar_refineria = fields.Boolean(compute='_compute_permisos')
    puede_editar_guias = fields.Boolean(compute='_compute_permisos')
    puede_editar_facturacion = fields.Boolean(compute='_compute_permisos')

    # ==================================================================
    #  Calculos
    # ==================================================================
    @api.depends('galones')
    def _compute_barriles(self):
        for cargue in self:
            cargue.barriles = round((cargue.galones or 0.0) / GALONES_POR_BARRIL, 2)

    @api.depends('precinto_ids.codigo', 'precinto_ids.estado')
    def _compute_precintos_texto(self):
        for cargue in self:
            usados = cargue.precinto_ids.filtered(lambda p: p.estado == 'USADO')
            cargue.precintos_texto = '-'.join(
                usados.sorted('numero').mapped('codigo'))

    @api.depends('refineria_completado_en')
    def _compute_refineria_bloqueado(self):
        limite = timedelta(minutes=CANDADO_MINUTOS)
        ahora = fields.Datetime.now()
        for cargue in self:
            cargue.refineria_bloqueado = bool(
                cargue.refineria_completado_en
                and ahora - cargue.refineria_completado_en > limite)

    @api.depends_context('uid')
    def _compute_permisos(self):
        usuario = self.env.user
        es_admin = usuario.has_group('conquers_operaciones.group_admin')
        permisos = {
            'puede_editar_logistica': es_admin or usuario.has_group(
                'conquers_operaciones.group_logistica'),
            'puede_editar_comercial': es_admin or usuario.has_group(
                'conquers_operaciones.group_comercial'),
            'puede_editar_refineria': es_admin or usuario.has_group(
                'conquers_operaciones.group_refineria'),
            'puede_editar_guias': es_admin or usuario.has_group(
                'conquers_operaciones.group_guias'),
            'puede_editar_facturacion': es_admin or usuario.has_group(
                'conquers_operaciones.group_facturacion'),
        }
        for cargue in self:
            cargue.update(permisos)

    # ==================================================================
    #  Autocompletado
    # ==================================================================
    @api.onchange('placa')
    def _onchange_placa(self):
        """Al digitar la placa se traen conductor, tanque y transportadora."""
        if not self.placa:
            return
        datos = self.env['operaciones.conductor'].buscar_por_placa(self.placa)
        if datos:
            self.update(datos)

    @api.onchange('conductor_id')
    def _onchange_conductor(self):
        if self.conductor_id:
            self.cedula_conductor = self.conductor_id.cedula
            self.celular_conductor = self.conductor_id.celular
            if not self.placa:
                self.placa = self.conductor_id.placa
            if not self.tanque:
                self.tanque = self.conductor_id.tanque

    # ==================================================================
    #  Permisos por campo y candado de refineria
    # ==================================================================
    def _verificar_permiso_campos(self, vals):
        """Bloquea en el servidor los campos que no son del area del usuario.

        Se aplica tambien cuando el usuario ataca por RPC, que es justo lo que
        no protege poner groups= en el XML de la vista.
        """
        if self.env.su or self.env.user.has_group('conquers_operaciones.group_admin'):
            return
        tocados = set(vals) - CAMPOS_LIBRES
        if not tocados:
            return
        permitidos = set()
        for grupo, campos in CAMPOS_POR_GRUPO.items():
            if self.env.user.has_group(grupo):
                permitidos |= campos
        negados = tocados - permitidos
        if negados:
            etiquetas = [self._fields[c].string if c in self._fields else c
                         for c in sorted(negados)]
            raise AccessError(_(
                'Su area no puede editar: %s') % ', '.join(etiquetas))

    def _verificar_candado_refineria(self, vals):
        """Pasados 30 minutos desde que refineria completo el viaje, sus datos
        quedan en firme y solo un administrador puede corregirlos."""
        if self.env.su or self.env.user.has_group('conquers_operaciones.group_admin'):
            return
        campos_candado = set(CAMPOS_REFINERIA) | {'precinto_ids', 'fecha_despacho'}
        if not (set(vals) & campos_candado):
            return
        for cargue in self:
            if cargue.refineria_bloqueado:
                raise UserError(_(
                    'Pasaron mas de %s minutos desde que refineria completo el '
                    'viaje de la placa %s. Pide a un administrador que lo '
                    'desbloquee.') % (CANDADO_MINUTOS, cargue.placa or '-'))

    def _actualizar_reloj_refineria(self):
        """Arranca el conteo cuando quedan todos los campos y lo reinicia si el
        viaje vuelve a quedar incompleto dentro de la ventana.

        El reinicio es lo que evita que un error de digitacion deje la fila
        muerta: si alguien borra un aforo por equivocacion dentro de los 30
        minutos, el reloj vuelve a cero en lugar de quedar corriendo.
        """
        ahora = fields.Datetime.now()
        limite = timedelta(minutes=CANDADO_MINUTOS)
        for cargue in self:
            completo = (all(cargue[c] for c in CAMPOS_REFINERIA)
                        and bool(cargue.precinto_ids))
            if completo and not cargue.refineria_completado_en:
                cargue.refineria_completado_en = ahora
            elif not completo and cargue.refineria_completado_en:
                if ahora - cargue.refineria_completado_en <= limite:
                    cargue.refineria_completado_en = False

    def write(self, vals):
        self._verificar_permiso_campos(vals)
        self._verificar_candado_refineria(vals)
        resultado = super().write(vals)
        if set(vals) & (set(CAMPOS_REFINERIA) | {'precinto_ids'}):
            self._actualizar_reloj_refineria()
        return resultado

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._verificar_permiso_campos(vals)
        return super().create(vals_list)

    def action_desbloquear_refineria(self):
        """Invalida el candado. Solo administradores."""
        if not self.env.user.has_group('conquers_operaciones.group_admin'):
            raise AccessError(_('Solo un administrador puede desbloquear el viaje.'))
        for cargue in self:
            cargue.refineria_completado_en = False
            cargue.message_post(body=_('Candado de refineria liberado por %s.')
                                % self.env.user.name)
        return True

    # ==================================================================
    #  Precintos
    # ==================================================================
    def _recalcular_precintos(self):
        self._compute_precintos_texto()
        self._actualizar_reloj_refineria()

    def action_asignar_precintos(self, cantidad=None, forzar=False):
        """Toma los siguientes N consecutivos disponibles y los pone en la fila."""
        self.ensure_one()
        cantidad = int(cantidad or PRECINTOS_CANTIDAD_DEFECTO)
        if not 1 <= cantidad <= PRECINTOS_CANTIDAD_MAXIMA:
            raise UserError(_('La cantidad debe estar entre 1 y %s.')
                            % PRECINTOS_CANTIDAD_MAXIMA)

        self._verificar_candado_refineria({'precinto_ids': True})

        ya_asignados = len(self.precinto_ids.filtered(lambda p: p.estado == 'USADO'))
        if ya_asignados and not forzar:
            raise UserError(_(
                'Esta fila ya tiene %s precintos asignados. Liberalos primero, o '
                'usa el asistente marcando "agregar de todas formas".'
            ) % ya_asignados)

        Precinto = self.env['operaciones.precinto']
        tomados = Precinto._tomar_disponibles(cantidad)
        if len(tomados) < cantidad:
            raise UserError(_(
                'Stock insuficiente: hay %s precintos disponibles y se pidieron '
                '%s. Registra un lote nuevo.') % (len(tomados), cantidad))

        tomados.marcar_usado(self)
        self._recalcular_precintos()

        codigos = tomados.sorted('numero').mapped('codigo')
        self.message_post(body=_('%s precintos asignados: %s')
                          % (len(codigos), '-'.join(codigos)))

        saltos = Precinto.detectar_saltos(self.id)
        if saltos:
            self.message_post(body=_(
                'Revisar: hay un salto en la numeracion entre %s.'
            ) % ', '.join('%s y %s' % (a, b) for a, b in saltos))
        return True

    def action_liberar_precintos(self):
        """Devuelve al stock los sellos de un viaje que se desprogramo."""
        self.ensure_one()
        self._verificar_candado_refineria({'precinto_ids': True})

        usados = self.precinto_ids.filtered(lambda p: p.estado == 'USADO')
        if not usados:
            raise UserError(_('Esta fila no tiene precintos del inventario.'))

        codigos = usados.sorted('numero').mapped('codigo')
        usados.liberar()
        self._recalcular_precintos()
        self.message_post(body=_('%s precintos devueltos al stock: %s')
                          % (len(codigos), '-'.join(codigos)))
        return True

    def action_abrir_asignar_precintos(self):
        """Abre el asistente para elegir una cantidad distinta de 5."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Asignar precintos'),
            'res_model': 'operaciones.asignar.precintos.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_cargue_id': self.id},
        }

    # ==================================================================
    #  Guia de transporte
    # ==================================================================
    @api.model
    def _extraer_folio_guia(self, texto):
        """Saca el folio de una guia fisica: '3034000000600-4' y '0600' dan 600."""
        if not texto:
            return None
        texto = str(texto).strip()
        # 1. Serie oficial de la guia fisica, con o sin digito de verificacion.
        encontrado = re.search(r'303400000?(\d{3,4})', texto)
        if encontrado:
            try:
                return int(encontrado.group(1))
            except (TypeError, ValueError):
                pass
        # 2. Folio suelto de 3 o 4 digitos. Se exige el rango real de folios
        #    para no confundirlo con una factura o con un ano.
        encontrado = re.match(r'^0*(\d{3,4})(?:-\d+)?$', texto)
        if encontrado:
            try:
                valor = int(encontrado.group(1))
                if GUIA_FISICA_FOLIO_MIN <= valor <= GUIA_FISICA_FOLIO_MAX:
                    return valor
            except (TypeError, ValueError):
                pass
        return None

    @api.model
    def siguiente_folio_guia_fisica(self):
        """El folio que sigue, mirando el historico de guias fisicas."""
        recientes = self.search(
            [('numero_guia', '!=', False)], order='id desc', limit=300)
        folios = [f for f in (self._extraer_folio_guia(c.numero_guia)
                              for c in recientes) if f is not None]
        siguiente = max(folios) + 1 if folios else GUIA_FISICA_FOLIO_INICIAL
        return '%04d' % siguiente

    def action_generar_guia(self):
        """Asigna el consecutivo de guia y abre el PDF para imprimir."""
        self.ensure_one()
        if not self.numero_guia:
            if self.tipo_guia == 'FISICA':
                folio = self.siguiente_folio_guia_fisica()
                self.numero_guia = '%s%s' % (GUIA_FISICA_SERIE, folio)
            else:
                self.numero_guia = self.env['ir.sequence'].next_by_code(
                    'operaciones.guia.digital')
            self.message_post(body=_('Guia generada: %s') % self.numero_guia)
            # El sello ya asignado hereda el numero de guia recien creado.
            self.precinto_ids.filtered(lambda p: p.estado == 'USADO').write(
                {'numero_guia': self.numero_guia})
        return self.env.ref(
            'conquers_operaciones.action_report_guia_transporte').report_action(self)

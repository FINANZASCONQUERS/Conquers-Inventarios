from datetime import date, datetime, timedelta

from odoo import api, fields, models

# Un candado abandonado (la operadora cerro el navegador) se suelta solo.
LOCK_TTL_MINUTOS = 2

# Canal por el que se avisa a las demas operadoras que una celda cambio.
CANAL_SABANA = 'operaciones_cargue'


class OperacionesCargueLock(models.Model):
    """Candado por celda para que cuatro areas editen la misma fila a la vez.

    Es el equivalente de programacion_cargue_locks del sistema actual. El tree
    editable de Odoo bloquea la fila entera y resuelve los choques con control
    optimista sobre write_date, que en esta sabana significa perder lo digitado
    varias veces al dia. Con candado por celda cada area escribe su columna sin
    tocar las de las demas.
    """
    _name = 'operaciones.cargue.lock'
    _description = 'Bloqueo de celda en edicion'

    cargue_id = fields.Many2one('operaciones.cargue', required=True,
                                ondelete='cascade', index=True)
    campo = fields.Char(required=True)
    usuario_id = fields.Many2one('res.users', required=True,
                                 default=lambda s: s.env.user)
    tomado_en = fields.Datetime(required=True, default=fields.Datetime.now,
                                index=True)

    _sql_constraints = [
        ('uq_cargue_campo', 'unique(cargue_id, campo)',
         'Esa celda ya esta siendo editada.'),
    ]

    @property
    def _limite_expiracion(self):
        return fields.Datetime.now() - timedelta(minutes=LOCK_TTL_MINUTOS)

    @api.autovacuum
    def _limpiar_expirados(self):
        self.search([('tomado_en', '<', self._limite_expiracion)]).unlink()

    @api.model
    def tomar(self, cargue_id, campo):
        """Intenta quedarse con la celda. Devuelve quien la tiene si esta ocupada."""
        existente = self.search([
            ('cargue_id', '=', cargue_id), ('campo', '=', campo),
        ], limit=1)
        if existente:
            if existente.tomado_en >= self._limite_expiracion:
                if existente.usuario_id == self.env.user:
                    existente.tomado_en = fields.Datetime.now()
                    return {'tomado': True}
                return {'tomado': False, 'usuario': existente.usuario_id.name}
            existente.unlink()
        self.create({'cargue_id': cargue_id, 'campo': campo})
        return {'tomado': True}

    @api.model
    def soltar(self, cargue_id, campo):
        self.search([
            ('cargue_id', '=', cargue_id), ('campo', '=', campo),
            ('usuario_id', '=', self.env.user.id),
        ]).unlink()
        return True

    @api.model
    def vigentes(self):
        """Los candados activos, para pintar las celdas ocupadas."""
        self.search([('tomado_en', '<', self._limite_expiracion)]).unlink()
        return [{
            'cargue_id': lock.cargue_id.id,
            'campo': lock.campo,
            'usuario': lock.usuario_id.name,
        } for lock in self.search([])]


class OperacionesCargueCelda(models.Model):
    """Escritura celda a celda, sin el control de concurrencia de Odoo."""
    _inherit = 'operaciones.cargue'

    def escribir_celda(self, campo, valor):
        """Guarda una sola celda y avisa a las demas operadoras.

        El chequeo de concurrencia de Odoo solo se dispara cuando el cliente
        manda __last_update junto con el registro completo. Al guardar por aqui
        el servidor hace un UPDATE de una columna y no hay conflicto que
        resolver, que es justo lo que permite que refineria escriba los galones
        mientras logistica escribe la placa en la misma fila.
        """
        self.ensure_one()
        if campo not in self._fields:
            raise ValueError('Campo desconocido: %s' % campo)

        # write() ya valida el permiso por area y el candado de 30 minutos.
        self.write({campo: valor})

        self.env['bus.bus']._sendone(CANAL_SABANA, 'celda_actualizada', {
            'id': self.id,
            'campo': campo,
            'valor': valor,
            'usuario': self.env.user.name,
        })
        guardado = self[campo]
        if isinstance(guardado, models.BaseModel):
            # Un Many2one no viaja como recordset: el cliente espera [id, nombre].
            guardado = ([guardado.id, guardado.display_name]
                        if guardado else False)
        elif isinstance(guardado, (date, datetime)):
            guardado = fields.Datetime.to_string(guardado) \
                if isinstance(guardado, datetime) \
                else fields.Date.to_string(guardado)

        return {
            'valor': guardado,
            # barriles y el texto de precintos se recalculan solos; el cliente
            # los necesita de vuelta para repintar sin recargar la sabana.
            'barriles': self.barriles,
            'precintos_texto': self.precintos_texto,
            'refineria_bloqueado': self.refineria_bloqueado,
        }

    @api.model
    def canal_sabana(self):
        return CANAL_SABANA

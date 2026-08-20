"""
Modelos del modulo DevTracker.

Convencion de valores almacenados: SIN tilde ('En Produccion', 'Critico'). La
tilde se agrega en la capa de presentacion. Un solo valor guardado evita que una
consulta falle por comparar 'En Produccion' contra 'En Producción'.

Convencion de fechas: los DateTime se guardan en UTC naive (ver tiempo.py). Los
campos que son Date puro (fecha_comprometida, fecha_deseada) no tienen ese
problema porque son fechas calendario acordadas, no instantes.
"""
from extensions import db

from dev_tracker.tiempo import (
    DIAS_AVISO_VENCIMIENTO,
    ahora_utc,
    fecha_bogota,
    hoy_bogota,
)

# --- Estados ---------------------------------------------------------------
# Previos al flujo de trabajo: viven en la bandeja de entrada, no en el tablero.
ESTADO_POR_REVISAR = 'Por revisar'
ESTADO_DEVUELTA = 'Devuelta'
ESTADO_RECHAZADA = 'Rechazada'
# Flujo de trabajo.
ESTADO_SOLICITADO = 'Solicitado'
ESTADO_EN_DESARROLLO = 'En Desarrollo'
ESTADO_EN_PRUEBAS = 'En Pruebas'
ESTADO_EN_PRODUCCION = 'En Produccion'
ESTADO_CANCELADO = 'Cancelado'

# FR-050: lo que esta aqui no cuenta como trabajo activo ni entra al calculo de
# cumplimiento de plazos. Son solicitudes que el desarrollador aun no acepto.
ESTADOS_PREVIOS = (ESTADO_POR_REVISAR, ESTADO_DEVUELTA, ESTADO_RECHAZADA)

# FR-027: una columna del tablero por cada uno de estos.
ESTADOS_TABLERO = (
    ESTADO_SOLICITADO,
    ESTADO_EN_DESARROLLO,
    ESTADO_EN_PRUEBAS,
    ESTADO_EN_PRODUCCION,
)

# Trabajo vivo: cuenta en "tickets activos" y puede estar retrasado.
ESTADOS_ACTIVOS = (ESTADO_SOLICITADO, ESTADO_EN_DESARROLLO, ESTADO_EN_PRUEBAS)

ESTADOS_VALIDOS = ESTADOS_PREVIOS + ESTADOS_TABLERO + (ESTADO_CANCELADO,)

PRIORIDADES = ('Alta', 'Media', 'Baja')

# 'Sin clasificar' es el estado de una falla reportada por el solicitante y que
# el desarrollador todavia no ha evaluado. Misma regla que con las fechas: ellos
# reportan, el desarrollador clasifica. Si el solicitante pudiera marcar
# 'Critico', controlaria el freno de despliegue (FR-021) y ese freno dejaria de
# significar algo.
SEVERIDAD_SIN_CLASIFICAR = 'Sin clasificar'
SEVERIDADES = ('Critico', 'Mayor', 'Menor')
SEVERIDADES_VALIDAS = SEVERIDADES + (SEVERIDAD_SIN_CLASIFICAR,)
# Orden para saber cual es "la mas alta" de un ticket.
PESO_SEVERIDAD = {'Critico': 3, 'Mayor': 2, 'Menor': 1, SEVERIDAD_SIN_CLASIFICAR: 0}
ETAPAS_DETECCION = ('Pruebas', 'Produccion')

ORIGEN_PORTAL = 'portal'
ORIGEN_DIRECTO = 'directo'

# Estados de plazo que devuelve DevTicket.estado_plazo
PLAZO_SIN_FECHA = 'sin_fecha'
PLAZO_A_TIEMPO = 'a_tiempo'
PLAZO_POR_VENCER = 'por_vencer'
PLAZO_RETRASADO = 'retrasado'
PLAZO_ENTREGADO_A_TIEMPO = 'entregado_a_tiempo'
PLAZO_ENTREGADO_TARDE = 'entregado_tarde'
PLAZO_NO_APLICA = 'no_aplica'


class DevTicket(db.Model):
    """Requerimiento de desarrollo. Elemento central del modulo."""

    __tablename__ = 'dev_tickets'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)

    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)

    # Firma del solicitante. Cuando origen='portal' sale de la sesion; cuando
    # origen='directo' el desarrollador la escribe (puede ser alguien sin cuenta).
    solicitante_nombre = db.Column(db.String(150), nullable=True)
    solicitante_email = db.Column(db.String(150), nullable=True, index=True)
    solicitante_area = db.Column(db.String(150), nullable=True)

    origen = db.Column(db.String(10), nullable=False, default=ORIGEN_DIRECTO)

    # Lo que el solicitante PROPONE (FR-041). Informativo, nunca compromiso.
    urgencia_propuesta = db.Column(db.String(10), nullable=True)
    fecha_deseada = db.Column(db.Date, nullable=True)

    # Lo que el desarrollador DEFINE.
    prioridad = db.Column(db.String(10), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default=ESTADO_POR_REVISAR, index=True)

    duplicado_de_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=True)
    # Ajuste o mejora pedida SOBRE un desarrollo ya entregado. Es un ticket
    # aparte, con su propia fecha comprometida, justamente para que la entrega
    # original conserve intacta su metrica de cumplimiento.
    relacionado_con_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=True)

    fecha_radicacion = db.Column(db.DateTime, nullable=True)
    fecha_solicitud = db.Column(db.DateTime, nullable=True)

    fecha_comprometida = db.Column(db.Date, nullable=True)
    # FR-004: se fija la PRIMERA vez que se asigna una fecha y no se vuelve a
    # tocar. Si se pudiera mover, correr la fecha "limpiaria" el incumplimiento.
    fecha_comprometida_original = db.Column(db.Date, nullable=True)

    fecha_inicio_desarrollo = db.Column(db.DateTime, nullable=True)
    fecha_entrada_pruebas = db.Column(db.DateTime, nullable=True)
    fecha_salida_produccion = db.Column(db.DateTime, nullable=True)

    notas_dev = db.Column(db.Text, nullable=True)

    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)

    bugs = db.relationship(
        'DevTicketBug', backref='ticket', lazy='select',
        cascade='all, delete-orphan', order_by='DevTicketBug.id',
    )
    checklist = db.relationship(
        'DevTicketChecklist', backref='ticket', lazy='select',
        cascade='all, delete-orphan', order_by='DevTicketChecklist.orden',
    )
    transiciones = db.relationship(
        'DevTicketTransition', backref='ticket', lazy='select',
        cascade='all, delete-orphan', order_by='DevTicketTransition.id',
    )
    resoluciones = db.relationship(
        'DevTriageResolution', backref='ticket', lazy='select',
        cascade='all, delete-orphan', order_by='DevTriageResolution.id',
    )

    # --- Derivados de plazo -------------------------------------------------

    @property
    def esta_entregado(self):
        return self.estado == ESTADO_EN_PRODUCCION

    @property
    def cuenta_para_plazos(self):
        """FR-050: solo lo aceptado entra al calculo de cumplimiento."""
        return self.estado not in ESTADOS_PREVIOS and self.estado != ESTADO_CANCELADO

    @property
    def fecha_entrega_real(self):
        """Fecha calendario en Bogota en que salio a produccion."""
        return fecha_bogota(self.fecha_salida_produccion)

    @property
    def dias_diferencia(self):
        """
        Dias contra la fecha comprometida, medidos en Bogota.

        Positivo = quedan dias / se entrego antes. Negativo = retraso.
        None si no hay compromiso de fecha (FR-003).
        """
        if not self.fecha_comprometida:
            return None
        referencia = self.fecha_entrega_real if self.esta_entregado else hoy_bogota()
        if referencia is None:
            referencia = hoy_bogota()
        return (self.fecha_comprometida - referencia).days

    @property
    def estado_plazo(self):
        """FR-012, FR-013, FR-016."""
        if not self.cuenta_para_plazos:
            return PLAZO_NO_APLICA
        if not self.fecha_comprometida:
            return PLAZO_SIN_FECHA
        dias = self.dias_diferencia
        if self.esta_entregado:
            return PLAZO_ENTREGADO_A_TIEMPO if dias >= 0 else PLAZO_ENTREGADO_TARDE
        if dias < 0:
            return PLAZO_RETRASADO
        if dias <= DIAS_AVISO_VENCIMIENTO:
            return PLAZO_POR_VENCER
        return PLAZO_A_TIEMPO

    @property
    def dias_restantes(self):
        dias = self.dias_diferencia
        return dias if dias is not None and dias >= 0 else None

    @property
    def dias_retraso(self):
        dias = self.dias_diferencia
        return -dias if dias is not None and dias < 0 else None

    @property
    def fecha_entrada_estado_actual(self):
        """Instante (UTC) de la ultima transicion hacia el estado actual."""
        ultima = None
        for t in self.transiciones:
            if t.estado_destino == self.estado:
                ultima = t
        if ultima:
            return ultima.fecha_transicion
        return self.fecha_solicitud or self.fecha_radicacion or self.creado_en

    @property
    def dias_en_estado_actual(self):
        """FR-017: cuanto lleva parado donde esta, util para lo estancado en pruebas."""
        entrada = fecha_bogota(self.fecha_entrada_estado_actual)
        if entrada is None:
            return None
        return (hoy_bogota() - entrada).days

    # --- Derivados de bugs y checklist --------------------------------------

    @property
    def bugs_abiertos(self):
        return [b for b in self.bugs if b.estado == 'Abierto']

    @property
    def total_bugs_abiertos(self):
        return len(self.bugs_abiertos)

    @property
    def fallas_sin_clasificar(self):
        """Reportes del solicitante a los que el desarrollador aun no da severidad."""
        return [b for b in self.bugs_abiertos
                if b.severidad == SEVERIDAD_SIN_CLASIFICAR]

    @property
    def severidad_maxima_abierta(self):
        """FR-020: la severidad mas alta entre los bugs abiertos."""
        abiertos = self.bugs_abiertos
        if not abiertos:
            return None
        return max(abiertos, key=lambda b: PESO_SEVERIDAD.get(b.severidad, 0)).severidad

    @property
    def tiene_criticos_abiertos(self):
        return any(b.severidad == 'Critico' for b in self.bugs_abiertos)

    @property
    def checklist_pendientes(self):
        return [c for c in self.checklist if not c.verificado]

    @property
    def checklist_progreso(self):
        """FR-024: (verificados, total)."""
        total = len(self.checklist)
        return (total - len(self.checklist_pendientes), total)

    def __repr__(self):
        return f'<DevTicket {self.code} {self.estado}>'


class DevTriageResolution(db.Model):
    """
    Decision del desarrollador sobre una solicitud radicada en el portal.

    Se guarda una fila por decision, no una por ticket: una solicitud puede ser
    devuelta, re-radicada y despues aceptada, y esa historia debe quedar.
    """

    __tablename__ = 'dev_triage_resolutions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=False, index=True)
    tipo = db.Column(db.String(20), nullable=False)  # aceptada | devuelta | rechazada
    comentario = db.Column(db.Text, nullable=True)
    fecha_resolucion = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    resuelto_por = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f'<DevTriageResolution {self.ticket_id} {self.tipo}>'


class DevTicketBug(db.Model):
    """
    Falla detectada sobre un ticket, en pruebas o ya en produccion.

    Puede nacer de dos formas: la registra el desarrollador, o la reporta el
    solicitante desde su portal. En el segundo caso entra como
    'Sin clasificar' y espera a que el desarrollador le ponga severidad.
    """

    __tablename__ = 'dev_ticket_bugs'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=False)
    severidad = db.Column(db.String(15), nullable=False, default='Menor')
    etapa_deteccion = db.Column(db.String(12), nullable=False, default='Pruebas')
    estado = db.Column(db.String(10), nullable=False, default='Abierto')
    fecha_deteccion = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    fecha_correccion = db.Column(db.DateTime, nullable=True)
    # Correo de quien la reportó. Vacío = la registró el desarrollador.
    reportado_por = db.Column(db.String(150), nullable=True)

    @property
    def sin_clasificar(self):
        return self.severidad == SEVERIDAD_SIN_CLASIFICAR

    def __repr__(self):
        return f'<DevTicketBug {self.id} {self.severidad} {self.estado}>'


class DevTicketChecklist(db.Model):
    """Punto de revision previo al despliegue, propio de un ticket."""

    __tablename__ = 'dev_ticket_checklists'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=False, index=True)
    texto = db.Column(db.String(300), nullable=False)
    verificado = db.Column(db.Boolean, nullable=False, default=False)
    fecha_verificacion = db.Column(db.DateTime, nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=0)
    # True = lo agrego el desarrollador para este ticket; False = vino de la plantilla.
    es_personalizado = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f'<DevTicketChecklist {self.id} {"OK" if self.verificado else "pendiente"}>'


class DevTicketTransition(db.Model):
    """
    Traza de cada cambio de estado (FR-010).

    Guarda tambien retrocesos y saltos de etapa (FR-009): un desarrollo que
    vuelve de produccion a desarrollo deja dos filas, no sobrescribe la primera.
    """

    __tablename__ = 'dev_ticket_transitions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=False, index=True)
    estado_origen = db.Column(db.String(20), nullable=True)
    estado_destino = db.Column(db.String(20), nullable=False)
    fecha_transicion = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    usuario_email = db.Column(db.String(150), nullable=True)

    def __repr__(self):
        return f'<DevTicketTransition {self.estado_origen}->{self.estado_destino}>'


class DevChecklistTemplate(db.Model):
    """
    Plantilla de puntos de revision que se copia a cada ticket nuevo.

    FR-026: se COPIA al crear el ticket, no se referencia. Por eso editar la
    plantilla no altera los tickets que ya existen.
    """

    __tablename__ = 'dev_checklist_templates'

    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.String(300), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<DevChecklistTemplate {self.orden} {self.texto[:30]}>'


# Puntos de revision con los que arranca el modulo si la tabla esta vacia.
CHECKLIST_POR_DEFECTO = [
    'Respaldo de la base de datos hecho',
    'Variables de entorno revisadas',
    'Permisos de usuario probados',
    'Logs de error revisados sin excepciones nuevas',
    'Prueba de regresion sobre modulos relacionados',
    'Probado en el navegador del solicitante',
]


def sembrar_checklist_por_defecto():
    """Carga la plantilla inicial. Idempotente: no hace nada si ya hay filas."""
    if DevChecklistTemplate.query.first() is not None:
        return 0
    for i, texto in enumerate(CHECKLIST_POR_DEFECTO):
        db.session.add(DevChecklistTemplate(texto=texto, orden=i, activo=True))
    db.session.commit()
    return len(CHECKLIST_POR_DEFECTO)


def siguiente_code():
    """
    Genera el siguiente codigo legible: DEV-001, DEV-002, ...

    Se calcula sobre el maximo existente en vez de contar filas, para que borrar
    un ticket no reutilice su codigo.
    """
    ultimo = (
        DevTicket.query
        .with_entities(DevTicket.code)
        .order_by(DevTicket.id.desc())
        .limit(50)
        .all()
    )
    maximo = 0
    for (code,) in ultimo:
        if code and code.startswith('DEV-'):
            try:
                maximo = max(maximo, int(code.split('-', 1)[1]))
            except (ValueError, IndexError):
                continue
    return f'DEV-{maximo + 1:03d}'


def copiar_checklist_de_plantilla(ticket):
    """Copia los puntos activos de la plantilla al ticket recien creado (FR-022)."""
    plantilla = (
        DevChecklistTemplate.query
        .filter_by(activo=True)
        .order_by(DevChecklistTemplate.orden)
        .all()
    )
    for item in plantilla:
        ticket.checklist.append(DevTicketChecklist(
            texto=item.texto,
            orden=item.orden,
            verificado=False,
            es_personalizado=False,
        ))


# ===========================================================================
# Notificaciones por correo
# ===========================================================================
# Regla del modulo: un correo sale solo si le da a la persona informacion que
# no tiene, que cambia lo que va a hacer, y que no provoco ella misma.
#
# Los correos NO se envian durante la peticion web: se escriben en esta cola y
# un trabajo del scheduler los manda despues. Eso da tres cosas gratis: la
# pantalla nunca se queda esperando al servidor de correo, un fallo de SMTP no
# rompe el guardado del ticket, y el retraso permite CANCELAR un aviso si el
# ticket volvio atras antes de que saliera.

EVENTO_ACEPTADA = 'triage_aceptada'
EVENTO_DEVUELTA = 'triage_devuelta'
EVENTO_RECHAZADA = 'triage_rechazada'
EVENTO_A_PRUEBAS = 'estado_pruebas_validar'
EVENTO_A_PRODUCCION = 'estado_produccion'
EVENTO_FALLA_PRODUCCION = 'falla_produccion'

# Minutos de gracia antes de enviar. Si el ticket se mueve de nuevo dentro de
# esta ventana, el aviso se cancela solo.
RETRASO_MINUTOS = {
    EVENTO_ACEPTADA: 10,
    EVENTO_DEVUELTA: 10,
    EVENTO_RECHAZADA: 10,
    EVENTO_A_PRUEBAS: 10,
    EVENTO_A_PRODUCCION: 10,
    # Las fallas en produccion se agrupan: si llegan varias seguidas, sale un
    # solo correo con todas.
    EVENTO_FALLA_PRODUCCION: 15,
}

CORREO_PENDIENTE = 'pendiente'
CORREO_ENVIANDO = 'enviando'
CORREO_ENVIADO = 'enviado'
CORREO_CANCELADO = 'cancelado'
CORREO_FALLIDO = 'fallido'


class DevEmailOutbox(db.Model):
    """Cola de correos por salir. Tambien es el registro anti-duplicados."""

    __tablename__ = 'dev_email_outbox'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('dev_tickets.id'), nullable=True, index=True)
    bug_id = db.Column(db.Integer, db.ForeignKey('dev_ticket_bugs.id'), nullable=True)
    evento = db.Column(db.String(40), nullable=False, index=True)
    destinatario = db.Column(db.String(150), nullable=False, index=True)
    programado_para = db.Column(db.DateTime, nullable=False, index=True)
    estado = db.Column(db.String(12), nullable=False, default=CORREO_PENDIENTE, index=True)
    intentos = db.Column(db.Integer, nullable=False, default=0)
    ultimo_error = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    enviado_en = db.Column(db.DateTime, nullable=True)

    ticket = db.relationship('DevTicket', foreign_keys=[ticket_id])
    bug = db.relationship('DevTicketBug', foreign_keys=[bug_id])

    def __repr__(self):
        return f'<DevEmailOutbox {self.evento} -> {self.destinatario} [{self.estado}]>'


class DevEmailPref(db.Model):
    """
    Interruptor de correos por persona.

    Ausencia de fila = activo. Asi nadie queda sin avisos por no haber entrado
    nunca a configurar nada.
    """

    __tablename__ = 'dev_email_prefs'

    email = db.Column(db.String(150), primary_key=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc)


def correos_activos_para(email):
    """True si esa persona quiere recibir avisos. Por defecto si."""
    if not email:
        return False
    pref = db.session.get(DevEmailPref, email)
    return True if pref is None else bool(pref.activo)

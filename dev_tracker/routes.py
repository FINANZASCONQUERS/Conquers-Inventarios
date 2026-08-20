"""
Rutas del modulo DevTracker: dos portales sobre una misma base de datos.

  /solicitudes   -> cualquier usuario con sesion. Radica requerimientos y
                    consulta el avance de LOS SUYOS.
  /dev-tracker   -> solo los correos de DEVTRACKER_ADMIN_EMAILS. Bandeja de
                    triage, tablero, bugs, checklist y metricas.

Regla de autoridad: el solicitante PROPONE urgencia y fecha deseada; solo el
desarrollador COMPROMETE prioridad y fecha de entrega (FR-041). Esto se impone
aqui, en el servidor, no escondiendo campos del formulario.
"""
import csv
import io
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint, Response, current_app, jsonify, redirect,
    render_template, request, session, url_for,
)
from werkzeug.routing import BuildError

from extensions import db
from dev_tracker.models import (
    ESTADOS_ACTIVOS,
    ESTADOS_TABLERO,
    ESTADOS_VALIDOS,
    ESTADO_CANCELADO,
    ESTADO_DEVUELTA,
    ESTADO_EN_DESARROLLO,
    ESTADO_EN_PRODUCCION,
    ESTADO_EN_PRUEBAS,
    ESTADO_POR_REVISAR,
    ESTADO_RECHAZADA,
    ESTADO_SOLICITADO,
    ETAPAS_DETECCION,
    ORIGEN_DIRECTO,
    ORIGEN_PORTAL,
    PLAZO_POR_VENCER,
    PLAZO_RETRASADO,
    PRIORIDADES,
    SEVERIDADES,
    SEVERIDAD_SIN_CLASIFICAR,
    EVENTO_ACEPTADA,
    EVENTO_A_PRODUCCION,
    EVENTO_A_PRUEBAS,
    EVENTO_DEVUELTA,
    EVENTO_FALLA_PRODUCCION,
    EVENTO_RECHAZADA,
    DevEmailPref,
    correos_activos_para,
    DevChecklistTemplate,
    DevTicket,
    DevTicketBug,
    DevTicketChecklist,
    DevTicketTransition,
    DevTriageResolution,
    copiar_checklist_de_plantilla,
    sembrar_checklist_por_defecto,
    siguiente_code,
)
from dev_tracker.notificaciones import encolar
from dev_tracker.tiempo import (
    DIAS_VENTANA_PRODUCCION,
    ahora_utc,
    fecha_bogota,
    hoy_bogota,
    iso,
    parse_fecha,
)

dev_tracker_bp = Blueprint('dev_tracker_bp', __name__)

# Lista blanca por correo, no por rol. En este sistema rol='admin' significa
# "ve todo el inventario" (lo tienen 3 personas), no "es el desarrollador".
DEVTRACKER_ADMIN_EMAILS_DEFAULT = ['numbers@conquerstrading.com']

# Solo para mostrar: en la BD los valores van sin tilde.
ETIQUETA_ESTADO = {
    ESTADO_POR_REVISAR: 'Por revisar',
    ESTADO_DEVUELTA: 'Devuelta',
    ESTADO_RECHAZADA: 'Rechazada',
    ESTADO_SOLICITADO: 'Solicitado',
    ESTADO_EN_DESARROLLO: 'En Desarrollo',
    ESTADO_EN_PRUEBAS: 'En Pruebas',
    ESTADO_EN_PRODUCCION: 'En Producción',
    ESTADO_CANCELADO: 'Cancelado',
}
ETIQUETA_SEVERIDAD = {
    'Critico': 'Crítico',
    'Mayor': 'Mayor',
    'Menor': 'Menor',
    SEVERIDAD_SIN_CLASIFICAR: 'Sin clasificar',
}

# Estados en los que el solicitante ya puede VER el desarrollo funcionando y por
# tanto puede reportar una falla o pedir un ajuste sobre el.
ESTADOS_REVISABLES = (ESTADO_EN_PRUEBAS, ESTADO_EN_PRODUCCION)


# --- Guardas de acceso ------------------------------------------------------

def _correos_autorizados():
    valores = current_app.config.get(
        'DEVTRACKER_ADMIN_EMAILS', DEVTRACKER_ADMIN_EMAILS_DEFAULT)
    return {str(e).strip().lower() for e in valores}


def _es_peticion_api():
    return request.path.startswith('/api/')


def _no_autenticado():
    if _es_peticion_api():
        return jsonify(success=False, message='Sesión requerida.'), 401
    try:
        return redirect(url_for('login', next=request.url))
    except BuildError:
        # La app de tests no monta el endpoint 'login'.
        return jsonify(success=False, message='Sesión requerida.'), 401


def login_requerido(f):
    """Copia local del guard de app.py. Local para no importar app (circular)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()
        return f(*args, **kwargs)
    return wrapper


def devtracker_admin_requerido(f):
    """Espacio de trabajo del desarrollador. 401 sin sesión, 403 sin permiso."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'email' not in session:
            return _no_autenticado()
        if session.get('email', '').strip().lower() not in _correos_autorizados():
            return jsonify(
                success=False,
                message='Esta sección es del espacio de trabajo de desarrollo.',
            ), 403
        return f(*args, **kwargs)
    return wrapper


def _usuario_actual():
    return {
        'email': session.get('email', ''),
        'nombre': session.get('nombre', ''),
        'area': session.get('area', []),
    }


def _area_texto(area):
    if isinstance(area, (list, tuple)):
        return ', '.join(str(a) for a in area) if area else None
    return str(area) if area else None


# --- Serializacion ----------------------------------------------------------

def _serializar_bug(b, con_ticket=False):
    datos = {
        'id': b.id,
        'descripcion': b.descripcion,
        'severidad': b.severidad,
        'severidad_label': ETIQUETA_SEVERIDAD.get(b.severidad, b.severidad),
        'sin_clasificar': b.sin_clasificar,
        'etapa_deteccion': b.etapa_deteccion,
        'estado': b.estado,
        'fecha_deteccion': iso(b.fecha_deteccion),
        'fecha_correccion': iso(b.fecha_correccion),
        'reportado_por': b.reportado_por,
    }
    if con_ticket and b.ticket is not None:
        datos['ticket_id'] = b.ticket.id
        datos['ticket_code'] = b.ticket.code
        datos['ticket_titulo'] = b.ticket.titulo
        datos['ticket_estado'] = b.ticket.estado
    return datos


def _serializar_item_checklist(c):
    return {
        'id': c.id,
        'texto': c.texto,
        'verificado': c.verificado,
        'fecha_verificacion': iso(c.fecha_verificacion),
        'es_personalizado': c.es_personalizado,
    }


def _serializar_transicion(t):
    return {
        'estado_origen': t.estado_origen,
        'estado_destino': t.estado_destino,
        'fecha': iso(t.fecha_transicion),
        'usuario': t.usuario_email,
    }


def _ultima_resolucion(t):
    return t.resoluciones[-1] if t.resoluciones else None


def _code_de(ticket_id):
    """Codigo legible de un ticket referenciado (DEV-005), o None."""
    if not ticket_id:
        return None
    otro = db.session.get(DevTicket, ticket_id)
    return otro.code if otro else None


def _ticket_dev(t, completo=False):
    """Payload para el espacio del desarrollador: todo."""
    verificados, total = t.checklist_progreso
    datos = {
        'id': t.id,
        'code': t.code,
        'titulo': t.titulo,
        'descripcion': t.descripcion,
        'solicitante_nombre': t.solicitante_nombre,
        'solicitante_email': t.solicitante_email,
        'solicitante_area': t.solicitante_area,
        'origen': t.origen,
        'urgencia_propuesta': t.urgencia_propuesta,
        'fecha_deseada': iso(t.fecha_deseada),
        'prioridad': t.prioridad,
        'estado': t.estado,
        'estado_label': ETIQUETA_ESTADO.get(t.estado, t.estado),
        'duplicado_de_id': t.duplicado_de_id,
        'relacionado_con_id': t.relacionado_con_id,
        'relacionado_con_code': _code_de(t.relacionado_con_id),
        'fecha_radicacion': iso(t.fecha_radicacion),
        'fecha_solicitud': iso(t.fecha_solicitud),
        'fecha_comprometida': iso(t.fecha_comprometida),
        'fecha_comprometida_original': iso(t.fecha_comprometida_original),
        'fecha_comprometida_movida': bool(
            t.fecha_comprometida_original
            and t.fecha_comprometida
            and t.fecha_comprometida != t.fecha_comprometida_original
        ),
        'fecha_inicio_desarrollo': iso(t.fecha_inicio_desarrollo),
        'fecha_entrada_pruebas': iso(t.fecha_entrada_pruebas),
        'fecha_salida_produccion': iso(t.fecha_salida_produccion),
        'notas_dev': t.notas_dev,
        'estado_plazo': t.estado_plazo,
        'dias_restantes': t.dias_restantes,
        'dias_retraso': t.dias_retraso,
        'dias_en_estado_actual': t.dias_en_estado_actual,
        'bugs_abiertos': t.total_bugs_abiertos,
        'severidad_maxima': t.severidad_maxima_abierta,
        'fallas_sin_clasificar': len(t.fallas_sin_clasificar),
        'checklist_verificados': verificados,
        'checklist_total': total,
    }
    if completo:
        datos['bugs'] = [_serializar_bug(b) for b in t.bugs]
        datos['checklist'] = [_serializar_item_checklist(c) for c in t.checklist]
        datos['transiciones'] = [_serializar_transicion(x) for x in t.transiciones]
        datos['resoluciones'] = [{
            'tipo': r.tipo,
            'comentario': r.comentario,
            'fecha': iso(r.fecha_resolucion),
        } for r in t.resoluciones]
    return datos


def _ticket_publico(t):
    """
    Payload para el portal del solicitante (FR-051, FR-052).

    Deliberadamente reducido: etapa y fechas. Nunca bugs, checklist, notas
    internas ni metricas del desarrollador.
    """
    resolucion = _ultima_resolucion(t)
    comentario = None
    if t.estado in (ESTADO_DEVUELTA, ESTADO_RECHAZADA) and resolucion:
        comentario = resolucion.comentario

    # Sus propios reportes de falla si los devolvemos: son datos que el mismo
    # escribio, no el detalle interno de errores del desarrollador. Verlos le
    # evita reportar dos veces lo mismo.
    email = session.get('email', '')
    mis_reportes = [{
        'descripcion': b.descripcion,
        'fecha': iso(b.fecha_deteccion),
        'resuelto': b.estado == 'Corregido',
    } for b in t.bugs if b.reportado_por == email]

    return {
        'id': t.id,
        'code': t.code,
        'titulo': t.titulo,
        'descripcion': t.descripcion,
        'estado': t.estado,
        'estado_label': ETIQUETA_ESTADO.get(t.estado, t.estado),
        'urgencia_propuesta': t.urgencia_propuesta,
        'fecha_deseada': iso(t.fecha_deseada),
        'fecha_radicacion': iso(t.fecha_radicacion),
        'fecha_comprometida': iso(t.fecha_comprometida),
        'fecha_salida_produccion': iso(t.fecha_salida_produccion),
        'entregado': t.esta_entregado,
        'comentario_dev': comentario,
        'relacionado_con_code': _code_de(t.relacionado_con_id),
        'puede_re_radicar': t.estado == ESTADO_DEVUELTA,
        # Solo tiene sentido reportar o pedir ajustes sobre algo que ya se
        # puede ver funcionando.
        'puede_reportar_falla': t.estado in ESTADOS_REVISABLES,
        'puede_solicitar_ajuste': t.estado in ESTADOS_REVISABLES,
        'mis_reportes': mis_reportes,
    }


def _registrar_transicion(ticket, origen, destino):
    db.session.add(DevTicketTransition(
        ticket=ticket,
        estado_origen=origen,
        estado_destino=destino,
        fecha_transicion=ahora_utc(),
        usuario_email=session.get('email'),
    ))


# ===========================================================================
# PORTAL DE SOLICITUDES  (todo usuario con sesion)
# ===========================================================================

@dev_tracker_bp.route('/solicitudes', methods=['GET'])
@login_requerido
def portal_solicitudes():
    return render_template(
        'dev_tracker/solicitudes.html',
        prioridades=PRIORIDADES,
        usuario=_usuario_actual(),
    )


@dev_tracker_bp.route('/api/solicitudes', methods=['POST'])
@login_requerido
def api_radicar_solicitud():
    """
    Radica un requerimiento (FR-039, FR-040, FR-041, FR-042).

    Solo se leen los cuatro campos permitidos. Si el payload trae prioridad,
    fecha_comprometida, estado u origen, se descartan sin aviso: esos los define
    el desarrollador en el triage.
    """
    datos = request.get_json(silent=True) or request.form or {}

    titulo = (datos.get('titulo') or '').strip()
    if not titulo:
        return jsonify(success=False, message='El título es obligatorio.'), 400

    urgencia = (datos.get('urgencia_propuesta') or '').strip() or None
    if urgencia and urgencia not in PRIORIDADES:
        return jsonify(
            success=False,
            message=f'Urgencia inválida. Use una de: {", ".join(PRIORIDADES)}.',
        ), 400

    usuario = _usuario_actual()
    ahora = ahora_utc()

    ticket = DevTicket(
        code=siguiente_code(),
        titulo=titulo[:200],
        descripcion=(datos.get('descripcion') or '').strip() or None,
        solicitante_nombre=usuario['nombre'] or usuario['email'],
        solicitante_email=usuario['email'],
        solicitante_area=_area_texto(usuario['area']),
        origen=ORIGEN_PORTAL,
        urgencia_propuesta=urgencia,
        fecha_deseada=parse_fecha(datos.get('fecha_deseada')),
        # Impuesto por el servidor, no por el cliente:
        prioridad=None,
        estado=ESTADO_POR_REVISAR,
        fecha_radicacion=ahora,
        creado_en=ahora,
        actualizado_en=ahora,
    )
    db.session.add(ticket)
    db.session.flush()
    _registrar_transicion(ticket, None, ESTADO_POR_REVISAR)
    db.session.commit()

    return jsonify(success=True, solicitud=_ticket_publico(ticket)), 201


@dev_tracker_bp.route('/api/solicitudes/mias', methods=['GET'])
@login_requerido
def api_mis_solicitudes():
    """FR-051: cada quien ve unicamente lo que el mismo radico."""
    email = session.get('email', '')
    tickets = (
        DevTicket.query
        .filter(DevTicket.solicitante_email == email)
        .order_by(DevTicket.id.desc())
        .all()
    )
    return jsonify(success=True, solicitudes=[_ticket_publico(t) for t in tickets])


@dev_tracker_bp.route('/api/solicitudes/<int:ticket_id>', methods=['GET'])
@login_requerido
def api_detalle_solicitud(ticket_id):
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Solicitud no encontrada.'), 404
    if (ticket.solicitante_email or '') != session.get('email', ''):
        return jsonify(success=False, message='Esta solicitud no es suya.'), 403
    return jsonify(success=True, solicitud=_ticket_publico(ticket))


@dev_tracker_bp.route('/api/solicitudes/<int:ticket_id>/re-radicar', methods=['PUT'])
@login_requerido
def api_re_radicar(ticket_id):
    """
    FR-049: completar y reenviar una solicitud devuelta, sobre el mismo registro.

    Dos condiciones, ambas necesarias: que sea suya, y que este en 'Devuelta'.
    Sin la segunda, cualquiera podria reescribir un ticket que ya esta en
    desarrollo y cambiarle el alcance por debajo.
    """
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Solicitud no encontrada.'), 404
    if (ticket.solicitante_email or '') != session.get('email', ''):
        return jsonify(success=False, message='Esta solicitud no es suya.'), 403
    if ticket.estado != ESTADO_DEVUELTA:
        return jsonify(
            success=False,
            message='Solo se pueden reenviar las solicitudes devueltas.',
        ), 409

    datos = request.get_json(silent=True) or request.form or {}
    if datos.get('titulo'):
        ticket.titulo = str(datos['titulo']).strip()[:200]
    if 'descripcion' in datos:
        ticket.descripcion = (datos.get('descripcion') or '').strip() or None
    if datos.get('urgencia_propuesta') in PRIORIDADES:
        ticket.urgencia_propuesta = datos['urgencia_propuesta']
    if 'fecha_deseada' in datos:
        ticket.fecha_deseada = parse_fecha(datos.get('fecha_deseada'))

    _registrar_transicion(ticket, ESTADO_DEVUELTA, ESTADO_POR_REVISAR)
    ticket.estado = ESTADO_POR_REVISAR
    ticket.actualizado_en = ahora_utc()
    db.session.commit()

    return jsonify(success=True, solicitud=_ticket_publico(ticket))


@dev_tracker_bp.route('/api/solicitudes/preferencias-correo', methods=['GET', 'POST'])
@login_requerido
def api_preferencias_correo():
    """Interruptor de avisos por correo. Cada quien controla solo el suyo."""
    email = session.get('email', '')

    if request.method == 'GET':
        return jsonify(success=True, activo=correos_activos_para(email))

    datos = request.get_json(silent=True) or {}
    activo = bool(datos.get('activo'))

    pref = db.session.get(DevEmailPref, email)
    if pref is None:
        pref = DevEmailPref(email=email, activo=activo)
        db.session.add(pref)
    else:
        pref.activo = activo
    pref.actualizado_en = ahora_utc()
    db.session.commit()

    return jsonify(success=True, activo=activo)


def _mi_ticket_o_error(ticket_id):
    """Carga un ticket verificando que sea del usuario en sesión."""
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return None, (jsonify(success=False, message='Solicitud no encontrada.'), 404)
    if (ticket.solicitante_email or '') != session.get('email', ''):
        return None, (jsonify(success=False, message='Esta solicitud no es suya.'), 403)
    return ticket, None


@dev_tracker_bp.route('/api/solicitudes/<int:ticket_id>/reportar-falla', methods=['POST'])
@login_requerido
def api_reportar_falla(ticket_id):
    """
    Caso A: "lo que me entregaste no funciona".

    La falla se registra SOBRE el ticket original, porque pertenece a ese
    desarrollo. Entra como 'Sin clasificar': el solicitante reporta, el
    desarrollador decide la severidad. Si el solicitante pudiera marcar
    'Critico', controlaria el freno de despliegue (FR-021) desde afuera.

    El ticket NO cambia de estado solo: devolverlo a desarrollo es decision del
    desarrollador. Y la fecha de la entrega original queda intacta, para que una
    falla encontrada despues no convierta retroactivamente en tardia una entrega
    que si fue a tiempo.
    """
    ticket, error = _mi_ticket_o_error(ticket_id)
    if error:
        return error
    if ticket.estado not in ESTADOS_REVISABLES:
        return jsonify(
            success=False,
            message='Solo se pueden reportar fallas de algo que ya esté en pruebas o entregado.',
        ), 409

    datos = request.get_json(silent=True) or request.form or {}
    descripcion = (datos.get('descripcion') or '').strip()
    if not descripcion:
        return jsonify(success=False, message='Describa qué le está fallando.'), 400

    bug = DevTicketBug(
        ticket=ticket,
        descripcion=descripcion,
        severidad=SEVERIDAD_SIN_CLASIFICAR,
        etapa_deteccion=('Produccion' if ticket.estado == ESTADO_EN_PRODUCCION else 'Pruebas'),
        estado='Abierto',
        fecha_deteccion=ahora_utc(),
        reportado_por=session.get('email'),
    )
    db.session.add(bug)
    ticket.actualizado_en = ahora_utc()
    db.session.flush()

    # Una falla sobre algo que YA está en producción no puede esperar al resumen
    # de mañana. Las de pruebas sí: ahí el desarrollo todavía no lo usa nadie.
    if ticket.estado == ESTADO_EN_PRODUCCION:
        for admin in _correos_autorizados():
            encolar(EVENTO_FALLA_PRODUCCION, ticket, admin, bug=bug)
    db.session.commit()

    return jsonify(success=True, solicitud=_ticket_publico(ticket)), 201


@dev_tracker_bp.route('/api/solicitudes/<int:ticket_id>/solicitar-ajuste', methods=['POST'])
@login_requerido
def api_solicitar_ajuste(ticket_id):
    """
    Caso B: "sí funciona, pero ahora lo quiero de otra forma".

    Crea un ticket NUEVO vinculado al original en vez de reabrir aquel. Si se
    reabriera, el tablero diria que ese desarrollo tomo semanas cuando en
    realidad se entrego a tiempo y lo que vino despues fue un requerimiento
    distinto. El ajuste lleva su propia fecha comprometida.
    """
    original, error = _mi_ticket_o_error(ticket_id)
    if error:
        return error
    if original.estado not in ESTADOS_REVISABLES:
        return jsonify(
            success=False,
            message='Solo se piden ajustes sobre algo que ya esté en pruebas o entregado.',
        ), 409

    datos = request.get_json(silent=True) or request.form or {}
    titulo = (datos.get('titulo') or '').strip()
    if not titulo:
        return jsonify(success=False, message='Escriba qué ajuste necesita.'), 400

    urgencia = (datos.get('urgencia_propuesta') or '').strip() or None
    if urgencia and urgencia not in PRIORIDADES:
        return jsonify(success=False, message='Urgencia inválida.'), 400

    usuario = _usuario_actual()
    ahora = ahora_utc()

    ajuste = DevTicket(
        code=siguiente_code(),
        titulo=titulo[:200],
        descripcion=(datos.get('descripcion') or '').strip() or None,
        solicitante_nombre=usuario['nombre'] or usuario['email'],
        solicitante_email=usuario['email'],
        solicitante_area=_area_texto(usuario['area']),
        origen=ORIGEN_PORTAL,
        urgencia_propuesta=urgencia,
        fecha_deseada=parse_fecha(datos.get('fecha_deseada')),
        prioridad=None,
        estado=ESTADO_POR_REVISAR,
        relacionado_con_id=original.id,
        fecha_radicacion=ahora,
        creado_en=ahora,
        actualizado_en=ahora,
    )
    db.session.add(ajuste)
    db.session.flush()
    _registrar_transicion(ajuste, None, ESTADO_POR_REVISAR)
    db.session.commit()

    return jsonify(success=True, solicitud=_ticket_publico(ajuste)), 201


# ===========================================================================
# ESPACIO DE TRABAJO DEL DESARROLLADOR
# ===========================================================================

@dev_tracker_bp.route('/dev-tracker', methods=['GET'])
@devtracker_admin_requerido
def espacio_dev():
    return render_template(
        'dev_tracker/dev_tracker.html',
        estados_tablero=[(e, ETIQUETA_ESTADO[e]) for e in ESTADOS_TABLERO],
        prioridades=PRIORIDADES,
        severidades=[(s, ETIQUETA_SEVERIDAD[s]) for s in SEVERIDADES],
        etapas=ETAPAS_DETECCION,
        dias_ventana_produccion=DIAS_VENTANA_PRODUCCION,
    )


@dev_tracker_bp.route('/api/dev-tracker/inbox', methods=['GET'])
@devtracker_admin_requerido
def api_inbox():
    """
    Bandeja de entrada. Devuelve tres grupos:
      - pendientes: solicitudes que esperan tu decisión.
      - fallas_por_clasificar: fallas que reportaron sobre desarrollos ya
        entregados y a las que falta ponerles severidad.
      - esperando_solicitante: devueltas que la otra persona no ha completado.
        No son trabajo tuyo pendiente, pero conviene verlas para no perderlas.
    """
    pendientes = (
        DevTicket.query
        .filter(DevTicket.estado == ESTADO_POR_REVISAR)
        .order_by(DevTicket.fecha_radicacion.asc())
        .all()
    )
    devueltas = (
        DevTicket.query
        .filter(DevTicket.estado == ESTADO_DEVUELTA)
        .order_by(DevTicket.actualizado_en.asc())
        .all()
    )
    fallas = (
        DevTicketBug.query
        .filter(DevTicketBug.severidad == SEVERIDAD_SIN_CLASIFICAR,
                DevTicketBug.estado == 'Abierto')
        .order_by(DevTicketBug.fecha_deteccion.asc())
        .all()
    )
    return jsonify(
        success=True,
        total_pendientes=len(pendientes),
        total_fallas=len(fallas),
        # Lo que exige tu atención: solicitudes nuevas + fallas sin clasificar.
        total_por_atender=len(pendientes) + len(fallas),
        pendientes=[_ticket_dev(t, completo=True) for t in pendientes],
        fallas_por_clasificar=[_serializar_bug(b, con_ticket=True) for b in fallas],
        esperando_solicitante=[_ticket_dev(t) for t in devueltas],
    )


@dev_tracker_bp.route('/api/dev-tracker/inbox/<int:ticket_id>/resolve', methods=['POST'])
@devtracker_admin_requerido
def api_resolver_triage(ticket_id):
    """FR-044, FR-045: aceptar, devolver o rechazar una solicitud radicada."""
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Solicitud no encontrada.'), 404
    if ticket.estado != ESTADO_POR_REVISAR:
        return jsonify(
            success=False,
            message=f'La solicitud ya no está en la bandeja (estado: {ticket.estado}).',
        ), 409

    datos = request.get_json(silent=True) or request.form or {}
    accion = (datos.get('accion') or '').strip().lower()
    comentario = (datos.get('comentario') or '').strip() or None
    estado_previo = ticket.estado
    ahora = ahora_utc()

    if accion == 'aceptar':
        prioridad = (datos.get('prioridad') or '').strip()
        if prioridad not in PRIORIDADES:
            return jsonify(
                success=False,
                message=f'Al aceptar debe fijar la prioridad real: {", ".join(PRIORIDADES)}.',
            ), 400
        ticket.prioridad = prioridad
        fecha = parse_fecha(datos.get('fecha_comprometida'))
        if fecha:
            ticket.fecha_comprometida = fecha
            if ticket.fecha_comprometida_original is None:
                ticket.fecha_comprometida_original = fecha
        ticket.estado = ESTADO_SOLICITADO
        ticket.fecha_solicitud = ahora
        # El checklist se copia al entrar al flujo de trabajo, no al radicar:
        # una solicitud que se rechaza nunca necesito puntos de revision.
        if not ticket.checklist:
            copiar_checklist_de_plantilla(ticket)

    elif accion == 'devolver':
        if not comentario:
            return jsonify(
                success=False,
                message='Al devolver debe indicar qué falta.',
            ), 400
        ticket.estado = ESTADO_DEVUELTA

    elif accion == 'rechazar':
        if not comentario:
            return jsonify(
                success=False,
                message='Al rechazar debe indicar el motivo.',
            ), 400
        ticket.estado = ESTADO_RECHAZADA
        duplicado_de = datos.get('duplicado_de_id')
        if duplicado_de:
            try:
                otro = db.session.get(DevTicket, int(duplicado_de))
                if otro is not None and otro.id != ticket.id:
                    ticket.duplicado_de_id = otro.id
            except (TypeError, ValueError):
                pass

    else:
        return jsonify(
            success=False,
            message='Acción inválida. Use: aceptar, devolver o rechazar.',
        ), 400

    db.session.add(DevTriageResolution(
        ticket=ticket,
        tipo={'aceptar': 'aceptada', 'devolver': 'devuelta', 'rechazar': 'rechazada'}[accion],
        comentario=comentario,
        fecha_resolucion=ahora,
        resuelto_por=session.get('email'),
    ))
    _registrar_transicion(ticket, estado_previo, ticket.estado)
    ticket.actualizado_en = ahora

    # El aviso al solicitante se ENCOLA, no se envía aquí: la petición nunca
    # espera al servidor de correo y hay 10 minutos para deshacer.
    encolar(
        {'aceptar': EVENTO_ACEPTADA,
         'devolver': EVENTO_DEVUELTA,
         'rechazar': EVENTO_RECHAZADA}[accion],
        ticket,
        ticket.solicitante_email,
    )
    db.session.commit()

    return jsonify(success=True, ticket=_ticket_dev(ticket, completo=True))


@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>/reactivar', methods=['POST'])
@devtracker_admin_requerido
def api_reactivar(ticket_id):
    """
    Caso borde: un requerimiento rechazado que despues si se aprueba.

    Vuelve a la bandeja (no directo al tablero) para que pase por el triage
    normal y se le fije prioridad y fecha. Conserva toda su historia.
    """
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404
    if ticket.estado not in (ESTADO_RECHAZADA, ESTADO_CANCELADO):
        return jsonify(
            success=False,
            message='Solo se reactivan tickets rechazados o cancelados.',
        ), 409

    estado_previo = ticket.estado
    ticket.estado = ESTADO_POR_REVISAR
    ticket.duplicado_de_id = None
    _registrar_transicion(ticket, estado_previo, ESTADO_POR_REVISAR)
    ticket.actualizado_en = ahora_utc()
    db.session.commit()
    return jsonify(success=True, ticket=_ticket_dev(ticket, completo=True))


def _filtrar_y_ordenar(tickets, args):
    """Filtros que dependen de la fecha de Bogota o de un orden propio."""
    plazo = (args.get('plazo') or '').strip()
    if plazo:
        tickets = [t for t in tickets if t.estado_plazo == plazo]

    orden = (args.get('orden') or 'fecha_comprometida').strip()
    peso_prioridad = {'Alta': 0, 'Media': 1, 'Baja': 2}
    lejano = hoy_bogota().replace(year=hoy_bogota().year + 50)

    if orden == 'prioridad':
        tickets.sort(key=lambda t: (peso_prioridad.get(t.prioridad, 3), t.id))
    elif orden == 'estado':
        pos = {e: i for i, e in enumerate(ESTADOS_VALIDOS)}
        tickets.sort(key=lambda t: (pos.get(t.estado, 99), t.id))
    elif orden == 'fecha_solicitud':
        tickets.sort(key=lambda t: (t.fecha_solicitud or t.creado_en), reverse=True)
    else:  # fecha_comprometida: lo mas urgente primero, sin fecha al final
        tickets.sort(key=lambda t: (t.fecha_comprometida or lejano, t.id))
    return tickets


@dev_tracker_bp.route('/api/dev-tracker/tickets', methods=['GET'])
@devtracker_admin_requerido
def api_listar_tickets():
    """
    Tickets del tablero (FR-029, FR-030, FR-031, FR-033).

    Por defecto muestra el trabajo vivo MAS lo entregado en los ultimos 30 dias.
    Si se excluyera todo lo que esta en produccion, la cuarta columna del Kanban
    quedaria siempre vacia; y si no se excluyera nada, el tablero crece sin
    limite. Lo mas viejo se consulta con ?historico=true.
    """
    q = DevTicket.query

    estado = (request.args.get('estado') or '').strip()
    historico = (request.args.get('historico') or '').lower() in ('1', 'true', 'si', 'sí')

    if estado:
        if estado not in ESTADOS_VALIDOS:
            return jsonify(success=False, message='Estado inválido.'), 400
        q = q.filter(DevTicket.estado == estado)
    elif historico:
        q = q.filter(~DevTicket.estado.in_((ESTADO_POR_REVISAR, ESTADO_DEVUELTA)))
    else:
        q = q.filter(DevTicket.estado.in_(ESTADOS_TABLERO))

    prioridad = (request.args.get('prioridad') or '').strip()
    if prioridad:
        q = q.filter(DevTicket.prioridad == prioridad)

    origen = (request.args.get('origen') or '').strip()
    if origen in (ORIGEN_PORTAL, ORIGEN_DIRECTO):
        q = q.filter(DevTicket.origen == origen)

    solicitante = (request.args.get('solicitante') or '').strip()
    if solicitante:
        patron = f'%{solicitante}%'
        q = q.filter(db.or_(
            DevTicket.solicitante_nombre.ilike(patron),
            DevTicket.solicitante_email.ilike(patron),
        ))

    texto = (request.args.get('q') or '').strip()
    if texto:
        patron = f'%{texto}%'
        q = q.filter(db.or_(
            DevTicket.titulo.ilike(patron),
            DevTicket.descripcion.ilike(patron),
            DevTicket.solicitante_nombre.ilike(patron),
            DevTicket.code.ilike(patron),
        ))

    tickets = q.all()

    # La columna "En Produccion" solo muestra lo reciente, salvo en historico.
    if not historico and not estado:
        corte = hoy_bogota() - timedelta(days=DIAS_VENTANA_PRODUCCION)
        tickets = [
            t for t in tickets
            if t.estado != ESTADO_EN_PRODUCCION
            or (t.fecha_entrega_real or corte) >= corte
        ]

    tickets = _filtrar_y_ordenar(tickets, request.args)
    return jsonify(success=True, total=len(tickets),
                   tickets=[_ticket_dev(t) for t in tickets])


@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>', methods=['GET'])
@devtracker_admin_requerido
def api_detalle_ticket(ticket_id):
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404
    return jsonify(success=True, ticket=_ticket_dev(ticket, completo=True))


@dev_tracker_bp.route('/api/dev-tracker/tickets', methods=['POST'])
@devtracker_admin_requerido
def api_crear_ticket_directo():
    """FR-047: lo que llega por WhatsApp, correo o llamada. No pasa por bandeja."""
    datos = request.get_json(silent=True) or request.form or {}
    titulo = (datos.get('titulo') or '').strip()
    if not titulo:
        return jsonify(success=False, message='El título es obligatorio.'), 400

    prioridad = (datos.get('prioridad') or 'Media').strip()
    if prioridad not in PRIORIDADES:
        return jsonify(success=False, message='Prioridad inválida.'), 400

    ahora = ahora_utc()
    fecha = parse_fecha(datos.get('fecha_comprometida'))

    ticket = DevTicket(
        code=siguiente_code(),
        titulo=titulo[:200],
        descripcion=(datos.get('descripcion') or '').strip() or None,
        solicitante_nombre=(datos.get('solicitante_nombre') or '').strip() or None,
        solicitante_email=(datos.get('solicitante_email') or '').strip() or None,
        solicitante_area=(datos.get('solicitante_area') or '').strip() or None,
        origen=ORIGEN_DIRECTO,
        prioridad=prioridad,
        estado=ESTADO_SOLICITADO,
        fecha_solicitud=ahora,
        fecha_comprometida=fecha,
        fecha_comprometida_original=fecha,
        notas_dev=(datos.get('notas_dev') or '').strip() or None,
        creado_en=ahora,
        actualizado_en=ahora,
    )
    db.session.add(ticket)
    db.session.flush()
    copiar_checklist_de_plantilla(ticket)
    _registrar_transicion(ticket, None, ESTADO_SOLICITADO)
    db.session.commit()

    return jsonify(success=True, ticket=_ticket_dev(ticket, completo=True)), 201


def _advertencias_fechas(inicio, pruebas, produccion, comprometida, solicitud):
    """FR-011: incoherencias entre fechas. Devuelve textos, no excepciones."""
    avisos = []
    d_inicio = fecha_bogota(inicio)
    d_pruebas = fecha_bogota(pruebas)
    d_prod = fecha_bogota(produccion)
    d_solicitud = fecha_bogota(solicitud)

    if d_pruebas and d_inicio and d_pruebas < d_inicio:
        avisos.append('La entrada a pruebas es anterior al inicio de desarrollo.')
    if d_prod and d_pruebas and d_prod < d_pruebas:
        avisos.append('La salida a producción es anterior a la entrada a pruebas.')
    if d_prod and d_inicio and d_prod < d_inicio:
        avisos.append('La salida a producción es anterior al inicio de desarrollo.')
    if comprometida and d_solicitud and comprometida < d_solicitud:
        avisos.append('La fecha comprometida es anterior a la fecha de solicitud.')
    return avisos


@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>', methods=['PUT'])
@devtracker_admin_requerido
def api_actualizar_ticket(ticket_id):
    """
    Actualiza un ticket: datos, fechas y estado.

    Las advertencias (FR-011, FR-021, FR-025) no bloquean de forma definitiva:
    devuelven 409 con la lista de lo que esta mal y el cliente reintenta con
    confirmar=true. Es "advertir y exigir confirmacion explicita", no "prohibir".
    """
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404

    datos = request.get_json(silent=True) or request.form or {}
    confirmar = bool(datos.get('confirmar'))
    ahora = ahora_utc()

    nuevo_estado = (datos.get('estado') or '').strip() or ticket.estado
    if nuevo_estado not in ESTADOS_VALIDOS:
        return jsonify(success=False, message='Estado inválido.'), 400

    if 'prioridad' in datos:
        prioridad = (datos.get('prioridad') or '').strip()
        if prioridad and prioridad not in PRIORIDADES:
            return jsonify(success=False, message='Prioridad inválida.'), 400
        ticket.prioridad = prioridad or None

    # Fechas propuestas: se validan ANTES de tocar el objeto.
    prop_comprometida = (
        parse_fecha(datos.get('fecha_comprometida'))
        if 'fecha_comprometida' in datos else ticket.fecha_comprometida
    )
    prop_inicio = ticket.fecha_inicio_desarrollo
    prop_pruebas = ticket.fecha_entrada_pruebas
    prop_produccion = ticket.fecha_salida_produccion

    # FR-008: correccion manual de las fechas reales cuando se registra en diferido.
    for campo, nombre in (
        ('fecha_inicio_desarrollo', 'prop_inicio'),
        ('fecha_entrada_pruebas', 'prop_pruebas'),
        ('fecha_salida_produccion', 'prop_produccion'),
    ):
        if campo in datos:
            f = parse_fecha(datos.get(campo))
            valor = None
            if f:
                # Se guarda como instante UTC del mediodia local (12:00 Bogota =
                # 17:00 UTC), para que la fecha calendario en Bogota siga siendo
                # exactamente la que el usuario escribio, sin corrimiento de dia.
                valor = datetime(f.year, f.month, f.day, 17, 0, 0)
            if nombre == 'prop_inicio':
                prop_inicio = valor
            elif nombre == 'prop_pruebas':
                prop_pruebas = valor
            else:
                prop_produccion = valor

    # Al entrar a un estado se sella su fecha real si aun no existe. No se
    # sobrescribe: un ticket que vuelve de produccion a desarrollo conserva las
    # fechas del ciclo anterior; el nuevo ciclo queda en las transiciones.
    if nuevo_estado != ticket.estado:
        if nuevo_estado == ESTADO_EN_DESARROLLO and prop_inicio is None:
            prop_inicio = ahora
        elif nuevo_estado == ESTADO_EN_PRUEBAS and prop_pruebas is None:
            prop_pruebas = ahora
        elif nuevo_estado == ESTADO_EN_PRODUCCION and prop_produccion is None:
            prop_produccion = ahora

    advertencias = _advertencias_fechas(
        prop_inicio, prop_pruebas, prop_produccion,
        prop_comprometida, ticket.fecha_solicitud,
    )

    if nuevo_estado == ESTADO_EN_PRODUCCION and ticket.estado != ESTADO_EN_PRODUCCION:
        if ticket.tiene_criticos_abiertos:  # FR-021
            criticos = [b for b in ticket.bugs_abiertos if b.severidad == 'Critico']
            advertencias.append(
                f'Tiene {len(criticos)} error(es) crítico(s) sin corregir.')
        # Una falla reportada y no evaluada podría ser crítica. Advertir sin
        # clasificarla equivale a no haberla mirado.
        sin_clasificar = ticket.fallas_sin_clasificar
        if sin_clasificar:
            advertencias.append(
                f'Hay {len(sin_clasificar)} falla(s) reportada(s) que aún no ha clasificado.')
        pendientes = ticket.checklist_pendientes  # FR-025
        if pendientes:
            advertencias.append(
                'Puntos de revisión sin verificar: '
                + '; '.join(c.texto for c in pendientes[:5])
                + ('...' if len(pendientes) > 5 else '')
            )

    if advertencias and not confirmar:
        return jsonify(
            success=False,
            requiere_confirmacion=True,
            advertencias=advertencias,
            message='Revise las advertencias antes de continuar.',
        ), 409

    # A partir de aqui se aplica todo.
    if 'titulo' in datos and (datos.get('titulo') or '').strip():
        ticket.titulo = str(datos['titulo']).strip()[:200]
    if 'descripcion' in datos:
        ticket.descripcion = (datos.get('descripcion') or '').strip() or None
    if 'notas_dev' in datos:
        ticket.notas_dev = (datos.get('notas_dev') or '').strip() or None
    for campo in ('solicitante_nombre', 'solicitante_email', 'solicitante_area'):
        if campo in datos:
            setattr(ticket, campo, (datos.get(campo) or '').strip() or None)

    ticket.fecha_comprometida = prop_comprometida
    # FR-004: la original se fija la primera vez y no se vuelve a tocar. Si se
    # pudiera mover, correr la fecha borraria el incumplimiento.
    if ticket.fecha_comprometida_original is None and prop_comprometida:
        ticket.fecha_comprometida_original = prop_comprometida

    ticket.fecha_inicio_desarrollo = prop_inicio
    ticket.fecha_entrada_pruebas = prop_pruebas
    ticket.fecha_salida_produccion = prop_produccion

    if nuevo_estado != ticket.estado:
        _registrar_transicion(ticket, ticket.estado, nuevo_estado)
        ticket.estado = nuevo_estado
        if nuevo_estado in ESTADOS_TABLERO and ticket.fecha_solicitud is None:
            ticket.fecha_solicitud = ahora
        if nuevo_estado in ESTADOS_TABLERO and not ticket.checklist:
            copiar_checklist_de_plantilla(ticket)

        # Solo dos etapas le importan a quien pidió: cuando necesitas que lo
        # valide, y cuando ya lo puede usar. "En Desarrollo" no le sirve de nada
        # y por eso no manda correo.
        if nuevo_estado == ESTADO_EN_PRODUCCION:
            encolar(EVENTO_A_PRODUCCION, ticket, ticket.solicitante_email)
        elif nuevo_estado == ESTADO_EN_PRUEBAS and datos.get('solicitar_validacion'):
            encolar(EVENTO_A_PRUEBAS, ticket, ticket.solicitante_email)

    ticket.actualizado_en = ahora
    db.session.commit()

    return jsonify(success=True, advertencias=advertencias,
                   ticket=_ticket_dev(ticket, completo=True))


@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>', methods=['DELETE'])
@devtracker_admin_requerido
def api_eliminar_ticket(ticket_id):
    """FR-005: eliminar de verdad. Para cancelar, use PUT con estado=Cancelado."""
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404
    db.session.delete(ticket)
    db.session.commit()
    return jsonify(success=True)


# --- Bugs -------------------------------------------------------------------

@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>/bugs', methods=['POST'])
@devtracker_admin_requerido
def api_crear_bug(ticket_id):
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404

    datos = request.get_json(silent=True) or request.form or {}
    descripcion = (datos.get('descripcion') or '').strip()
    if not descripcion:
        return jsonify(success=False, message='Describa el error.'), 400

    severidad = (datos.get('severidad') or 'Menor').strip()
    if severidad not in SEVERIDADES:
        return jsonify(success=False, message='Severidad inválida.'), 400

    # Si no lo dicen, la etapa se deduce de donde esta el ticket (FR-018).
    etapa = (datos.get('etapa_deteccion') or '').strip()
    if etapa not in ETAPAS_DETECCION:
        etapa = 'Produccion' if ticket.estado == ESTADO_EN_PRODUCCION else 'Pruebas'

    bug = DevTicketBug(
        ticket=ticket,
        descripcion=descripcion,
        severidad=severidad,
        etapa_deteccion=etapa,
        estado='Abierto',
        fecha_deteccion=ahora_utc(),
    )
    db.session.add(bug)
    ticket.actualizado_en = ahora_utc()
    db.session.commit()
    return jsonify(success=True, bug=_serializar_bug(bug),
                   ticket=_ticket_dev(ticket, completo=True)), 201


@dev_tracker_bp.route('/api/dev-tracker/bugs/<int:bug_id>', methods=['PUT'])
@devtracker_admin_requerido
def api_actualizar_bug(bug_id):
    """FR-019: marcar corregido sin borrar el error del historial."""
    bug = db.session.get(DevTicketBug, bug_id)
    if bug is None:
        return jsonify(success=False, message='Error no encontrado.'), 404

    datos = request.get_json(silent=True) or request.form or {}
    if 'descripcion' in datos and (datos.get('descripcion') or '').strip():
        bug.descripcion = str(datos['descripcion']).strip()
    if datos.get('severidad') in SEVERIDADES:
        bug.severidad = datos['severidad']

    estado = (datos.get('estado') or '').strip()
    if estado == 'Corregido':
        bug.estado = 'Corregido'
        bug.fecha_correccion = ahora_utc()
    elif estado == 'Abierto':
        bug.estado = 'Abierto'
        bug.fecha_correccion = None
    elif estado:
        return jsonify(success=False, message='Estado de error inválido.'), 400

    bug.ticket.actualizado_en = ahora_utc()
    db.session.commit()
    return jsonify(success=True, bug=_serializar_bug(bug),
                   ticket=_ticket_dev(bug.ticket, completo=True))


# --- Checklist --------------------------------------------------------------

@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>/checklist/items', methods=['POST'])
@devtracker_admin_requerido
def api_agregar_item_checklist(ticket_id):
    """FR-023: agregar un punto propio de este ticket, sin tocar la plantilla."""
    ticket = db.session.get(DevTicket, ticket_id)
    if ticket is None:
        return jsonify(success=False, message='Ticket no encontrado.'), 404

    datos = request.get_json(silent=True) or request.form or {}
    texto = (datos.get('texto') or '').strip()
    if not texto:
        return jsonify(success=False, message='Escriba el punto a revisar.'), 400

    orden = max([c.orden for c in ticket.checklist], default=-1) + 1
    item = DevTicketChecklist(
        ticket=ticket, texto=texto[:300], orden=orden,
        verificado=False, es_personalizado=True,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(success=True, item=_serializar_item_checklist(item),
                   ticket=_ticket_dev(ticket, completo=True)), 201


@dev_tracker_bp.route(
    '/api/dev-tracker/tickets/<int:ticket_id>/checklist/items/<int:item_id>',
    methods=['DELETE'])
@devtracker_admin_requerido
def api_eliminar_item_checklist(ticket_id, item_id):
    item = db.session.get(DevTicketChecklist, item_id)
    if item is None or item.ticket_id != ticket_id:
        return jsonify(success=False, message='Punto de revisión no encontrado.'), 404
    ticket = item.ticket
    db.session.delete(item)
    db.session.commit()
    return jsonify(success=True, ticket=_ticket_dev(ticket, completo=True))


@dev_tracker_bp.route('/api/dev-tracker/tickets/<int:ticket_id>/checklist/toggle', methods=['PUT'])
@devtracker_admin_requerido
def api_toggle_checklist(ticket_id):
    datos = request.get_json(silent=True) or request.form or {}
    try:
        item_id = int(datos.get('item_id'))
    except (TypeError, ValueError):
        return jsonify(success=False, message='item_id requerido.'), 400

    item = db.session.get(DevTicketChecklist, item_id)
    if item is None or item.ticket_id != ticket_id:
        return jsonify(success=False, message='Punto de revisión no encontrado.'), 404

    verificado = datos.get('verificado')
    item.verificado = (not item.verificado) if verificado is None else bool(verificado)
    item.fecha_verificacion = ahora_utc() if item.verificado else None
    db.session.commit()
    return jsonify(success=True, item=_serializar_item_checklist(item),
                   ticket=_ticket_dev(item.ticket, completo=True))


# --- Plantilla de checklist -------------------------------------------------

@dev_tracker_bp.route('/api/dev-tracker/plantilla', methods=['GET', 'POST'])
@devtracker_admin_requerido
def api_plantilla():
    """
    FR-026: editar la plantilla no altera los tickets ya creados, porque los
    puntos se COPIAN al ticket cuando entra al flujo, no se referencian.
    """
    if request.method == 'GET':
        items = DevChecklistTemplate.query.order_by(DevChecklistTemplate.orden).all()
        return jsonify(success=True, plantilla=[
            {'id': i.id, 'texto': i.texto, 'orden': i.orden, 'activo': i.activo}
            for i in items
        ])

    datos = request.get_json(silent=True) or {}
    textos = datos.get('items')
    if not isinstance(textos, list):
        return jsonify(success=False, message='Envíe items como lista de textos.'), 400

    DevChecklistTemplate.query.delete()
    for i, texto in enumerate(textos):
        texto = str(texto).strip()
        if texto:
            db.session.add(DevChecklistTemplate(texto=texto[:300], orden=i, activo=True))
    db.session.commit()

    items = DevChecklistTemplate.query.order_by(DevChecklistTemplate.orden).all()
    return jsonify(success=True, plantilla=[
        {'id': i.id, 'texto': i.texto, 'orden': i.orden, 'activo': i.activo}
        for i in items
    ])


# --- Metricas y exportacion -------------------------------------------------

@dev_tracker_bp.route('/api/dev-tracker/metrics', methods=['GET'])
@devtracker_admin_requerido
def api_metricas():
    """
    FR-032. El porcentaje de cumplimiento se calcula solo sobre lo entregado, y
    excluye del todo las solicitudes que nunca se aceptaron (FR-050): contar una
    solicitud rechazada como incumplimiento seria falso.
    """
    todos = DevTicket.query.all()
    considerados = [t for t in todos if t.cuenta_para_plazos]

    activos = [t for t in considerados if t.estado in ESTADOS_ACTIVOS]
    entregados = [t for t in considerados
                  if t.estado == ESTADO_EN_PRODUCCION and t.fecha_comprometida]
    a_tiempo = [t for t in entregados if (t.dias_diferencia or 0) >= 0]

    por_estado = {e: 0 for e in ESTADOS_TABLERO}
    for t in considerados:
        if t.estado in por_estado:
            por_estado[t.estado] += 1

    bugs_abiertos = sum(t.total_bugs_abiertos for t in todos)
    criticos_abiertos = sum(
        1 for t in todos for b in t.bugs_abiertos if b.severidad == 'Critico')

    return jsonify(success=True, metricas={
        'total_activos': len(activos),
        'por_estado': por_estado,
        'retrasados': sum(1 for t in activos if t.estado_plazo == PLAZO_RETRASADO),
        'por_vencer': sum(1 for t in activos if t.estado_plazo == PLAZO_POR_VENCER),
        'en_pruebas': sum(1 for t in activos if t.estado == ESTADO_EN_PRUEBAS),
        'bugs_abiertos': bugs_abiertos,
        'criticos_abiertos': criticos_abiertos,
        'fallas_por_clasificar': sum(len(t.fallas_sin_clasificar) for t in todos),
        'bandeja_pendiente': sum(1 for t in todos if t.estado == ESTADO_POR_REVISAR),
        'esperando_solicitante': sum(1 for t in todos if t.estado == ESTADO_DEVUELTA),
        'entregados_total': len(entregados),
        'entregados_a_tiempo': len(a_tiempo),
        'pct_cumplimiento': (
            round(100.0 * len(a_tiempo) / len(entregados), 1) if entregados else None
        ),
    })


@dev_tracker_bp.route('/api/dev-tracker/export', methods=['GET'])
@devtracker_admin_requerido
def api_exportar():
    """FR-034. CSV por defecto (se abre en Excel); ?formato=json para el respaldo."""
    formato = (request.args.get('formato') or 'csv').strip().lower()
    tickets = DevTicket.query.order_by(DevTicket.id).all()
    marca = hoy_bogota().isoformat()

    if formato == 'json':
        return jsonify(
            generado=iso(ahora_utc()),
            total=len(tickets),
            tickets=[_ticket_dev(t, completo=True) for t in tickets],
        )

    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow([
        'Codigo', 'Titulo', 'Solicitante', 'Area', 'Origen', 'Prioridad', 'Estado',
        'Urgencia propuesta', 'Fecha deseada', 'Fecha radicacion', 'Fecha solicitud',
        'Fecha comprometida', 'Fecha comprometida original', 'Inicio desarrollo',
        'Entrada pruebas', 'Salida produccion', 'Estado plazo', 'Dias restantes',
        'Dias retraso', 'Bugs abiertos', 'Severidad maxima', 'Checklist',
    ])
    for t in tickets:
        verificados, total = t.checklist_progreso
        escritor.writerow([
            t.code, t.titulo, t.solicitante_nombre or '', t.solicitante_area or '',
            t.origen, t.prioridad or '', ETIQUETA_ESTADO.get(t.estado, t.estado),
            t.urgencia_propuesta or '', iso(t.fecha_deseada) or '',
            iso(t.fecha_radicacion) or '', iso(t.fecha_solicitud) or '',
            iso(t.fecha_comprometida) or '', iso(t.fecha_comprometida_original) or '',
            iso(t.fecha_inicio_desarrollo) or '', iso(t.fecha_entrada_pruebas) or '',
            iso(t.fecha_salida_produccion) or '', t.estado_plazo,
            t.dias_restantes if t.dias_restantes is not None else '',
            t.dias_retraso if t.dias_retraso is not None else '',
            t.total_bugs_abiertos, t.severidad_maxima_abierta or '',
            f'{verificados}/{total}',
        ])

    # utf-8-sig: sin el BOM, Excel abre las tildes como caracteres raros.
    return Response(
        salida.getvalue().encode('utf-8-sig'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename=devtracker_{marca}.csv'},
    )


def inicializar_dev_tracker(app):
    """Siembra la plantilla de checklist si esta vacía. Idempotente."""
    with app.app_context():
        try:
            sembrar_checklist_por_defecto()
        except Exception:
            db.session.rollback()

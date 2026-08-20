"""
Decide QUE se notifica, A QUIEN y CUANDO.

Tres reglas gobiernan todo este archivo:

1. Un correo sale solo si le da a la persona informacion que no tiene, que
   cambia lo que va a hacer. "Ya empezamos a trabajar" no cambia nada para
   quien pidio: no se manda.
2. Nadie recibe correo por algo que hizo el mismo. Quien acaba de radicar ya
   vio la confirmacion en pantalla.
3. Al desarrollador no se le manda un correo por evento, sino UN resumen al
   dia, y solo si hay algo que reportar. Dia tranquilo, bandeja limpia.

El retraso de 10 minutos no es pereza: es la ventana para deshacer. Si arrastras
un ticket a Produccion por error y lo devuelves, el aviso se cancela solo porque
al momento de enviar se vuelve a mirar el estado real del ticket.
"""
import html
import logging
from datetime import timedelta

from extensions import db
from dev_tracker.correo import (
    COLOR_ALERTA,
    COLOR_EXITO,
    COLOR_PELIGRO,
    COLOR_PRIMARIO,
    _boton,
    enviar_smtp,
    envolver,
    tabla_datos,
)
from dev_tracker.models import (
    CORREO_CANCELADO,
    CORREO_ENVIADO,
    CORREO_ENVIANDO,
    CORREO_FALLIDO,
    CORREO_PENDIENTE,
    ESTADOS_ACTIVOS,
    ESTADO_DEVUELTA,
    ESTADO_EN_PRODUCCION,
    ESTADO_EN_PRUEBAS,
    ESTADO_POR_REVISAR,
    ESTADO_RECHAZADA,
    EVENTO_ACEPTADA,
    EVENTO_A_PRODUCCION,
    EVENTO_A_PRUEBAS,
    EVENTO_DEVUELTA,
    EVENTO_FALLA_PRODUCCION,
    EVENTO_RECHAZADA,
    PLAZO_POR_VENCER,
    PLAZO_RETRASADO,
    RETRASO_MINUTOS,
    SEVERIDAD_SIN_CLASIFICAR,
    DevEmailOutbox,
    DevTicket,
    DevTicketBug,
    correos_activos_para,
)
from dev_tracker.tiempo import ahora_utc, hoy_bogota

log = logging.getLogger(__name__)

MAX_INTENTOS = 3

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def _e(texto):
    return html.escape(str(texto or ''))


def _fecha_larga(f):
    if not f:
        return None
    return '{} de {} de {}'.format(f.day, MESES[f.month - 1], f.year)


# ---------------------------------------------------------------------------
# Encolar
# ---------------------------------------------------------------------------

def encolar(evento, ticket, destinatario, bug=None):
    """
    Deja un correo listo para salir dentro de N minutos.

    No envia nada: solo escribe una fila. Si ya hay un aviso pendiente igual, o
    uno igual salio en las ultimas 12 horas, no hace nada. Eso cubre el doble
    clic, el reintento y el reinicio del servidor.
    """
    if not destinatario or not correos_activos_para(destinatario):
        return None

    ticket_id = ticket.id if ticket else None
    bug_id = bug.id if bug else None

    # La clave de duplicado incluye el bug: dos fallas distintas del mismo
    # ticket son dos avisos distintos, aunque despues salgan juntas en un solo
    # correo. Sin esto, la segunda falla que reporten se perderia.
    ya_pendiente = DevEmailOutbox.query.filter_by(
        ticket_id=ticket_id,
        bug_id=bug_id,
        evento=evento,
        destinatario=destinatario,
        estado=CORREO_PENDIENTE,
    ).first()
    if ya_pendiente:
        return ya_pendiente

    corte = ahora_utc() - timedelta(hours=12)
    ya_enviado = DevEmailOutbox.query.filter(
        DevEmailOutbox.ticket_id == ticket_id,
        DevEmailOutbox.bug_id.is_(None) if bug_id is None
        else DevEmailOutbox.bug_id == bug_id,
        DevEmailOutbox.evento == evento,
        DevEmailOutbox.destinatario == destinatario,
        DevEmailOutbox.estado == CORREO_ENVIADO,
        DevEmailOutbox.enviado_en >= corte,
    ).first()
    if ya_enviado:
        return None

    fila = DevEmailOutbox(
        ticket_id=ticket_id,
        bug_id=bug_id,
        evento=evento,
        destinatario=destinatario,
        programado_para=ahora_utc() + timedelta(minutes=RETRASO_MINUTOS.get(evento, 10)),
        estado=CORREO_PENDIENTE,
    )
    db.session.add(fila)
    return fila


# ---------------------------------------------------------------------------
# Vigencia: aqui es donde el aviso se cancela solo
# ---------------------------------------------------------------------------

def sigue_vigente(fila):
    """
    Al momento de enviar, se vuelve a mirar el estado real del ticket.

    Si se movio de nuevo dentro de la ventana de gracia, el aviso ya no
    corresponde y se cancela sin que el solicitante se entere de nada.
    """
    ticket = fila.ticket
    if ticket is None:
        return False

    if fila.evento == EVENTO_A_PRODUCCION:
        return ticket.estado == ESTADO_EN_PRODUCCION
    if fila.evento == EVENTO_A_PRUEBAS:
        return ticket.estado == ESTADO_EN_PRUEBAS
    if fila.evento == EVENTO_DEVUELTA:
        return ticket.estado == ESTADO_DEVUELTA
    if fila.evento == EVENTO_RECHAZADA:
        return ticket.estado == ESTADO_RECHAZADA
    if fila.evento == EVENTO_ACEPTADA:
        # Si volvio a la bandeja, la aceptacion ya no ocurrio.
        return ticket.estado not in (ESTADO_POR_REVISAR, ESTADO_DEVUELTA, ESTADO_RECHAZADA)
    if fila.evento == EVENTO_FALLA_PRODUCCION:
        return fila.bug is not None and fila.bug.estado == 'Abierto'
    return False


# ---------------------------------------------------------------------------
# Redaccion
# ---------------------------------------------------------------------------

def construir(fila):
    """Devuelve (asunto, html, texto) para una fila de la cola."""
    t = fila.ticket
    code, titulo = _e(t.code), _e(t.titulo)

    if fila.evento == EVENTO_ACEPTADA:
        fecha = _fecha_larga(t.fecha_comprometida)
        asunto = '[{}] Aceptada'.format(t.code)
        if t.fecha_comprometida:
            asunto += ' · entrega {}'.format(t.fecha_comprometida)
        cuerpo = (
            '<p>Tu solicitud <strong>{}</strong> quedó aceptada y ya está en cola '
            'de trabajo.</p>'.format(code)
            + tabla_datos([
                ('Requerimiento', titulo),
                ('Prioridad asignada', _e(t.prioridad)),
                ('Fecha de entrega', fecha or 'Sin fecha comprometida por ahora'),
            ])
            + '<p>Te avisamos cuando esté disponible. No tienes que hacer nada más.</p>'
        )
        texto = 'Tu solicitud {} ({}) fue aceptada.\nPrioridad: {}\nEntrega: {}'.format(
            t.code, t.titulo, t.prioridad, fecha or 'por definir')
        return asunto, envolver('Solicitud aceptada', COLOR_EXITO, cuerpo,
                                _boton('Ver mis solicitudes', '/solicitudes',
                                       COLOR_EXITO)), texto

    if fila.evento == EVENTO_DEVUELTA:
        comentario = t.resoluciones[-1].comentario if t.resoluciones else ''
        asunto = '[{}] Necesitamos más información'.format(t.code)
        cuerpo = (
            '<p>Para poder programar <strong>{}</strong> hace falta que completes '
            'algo:</p>'.format(code)
            + '<div style="margin:16px 0;padding:14px 16px;background:#fff8e6;'
              'border-left:3px solid {};border-radius:0 8px 8px 0;font-size:13px">'
              '{}</div>'.format(COLOR_ALERTA, _e(comentario))
            + '<p>Entra a tu portal, complétala y vuelve a enviarla desde el mismo '
              'requerimiento. <strong>Mientras no la reenvíes, queda detenida.</strong></p>'
        )
        texto = 'Tu solicitud {} ({}) fue devuelta.\nComentario: {}\n' \
                'Complétala y reenvíala desde tu portal.'.format(t.code, t.titulo, comentario)
        return asunto, envolver('Falta información', COLOR_ALERTA, cuerpo,
                                _boton('Completar solicitud', '/solicitudes',
                                       COLOR_ALERTA)), texto

    if fila.evento == EVENTO_RECHAZADA:
        motivo = t.resoluciones[-1].comentario if t.resoluciones else ''
        asunto = '[{}] No procede'.format(t.code)
        cuerpo = (
            '<p>Tu solicitud <strong>{}</strong> ({}) no se va a desarrollar.</p>'.format(
                code, titulo)
            + '<div style="margin:16px 0;padding:14px 16px;background:#fdf2f2;'
              'border-left:3px solid {};border-radius:0 8px 8px 0;font-size:13px">'
              '{}</div>'.format(COLOR_PELIGRO, _e(motivo))
            + '<p>Si crees que hay algo que no se tuvo en cuenta, respóndeme y lo miramos.</p>'
        )
        texto = 'Tu solicitud {} ({}) no procede.\nMotivo: {}'.format(
            t.code, t.titulo, motivo)
        return asunto, envolver('Solicitud no aprobada', COLOR_PELIGRO, cuerpo), texto

    if fila.evento == EVENTO_A_PRUEBAS:
        asunto = '[{}] Listo para que lo pruebes'.format(t.code)
        cuerpo = (
            '<p><strong>{}</strong> ya está funcionando y necesito que lo revises '
            'antes de dejarlo definitivo.</p>'.format(code)
            + tabla_datos([('Requerimiento', titulo)])
            + '<p>Pruébalo con un caso real. Si algo no funciona como esperabas, '
              'repórtalo desde tu portal con el botón <strong>"Me falla"</strong> '
              'del requerimiento.</p>'
        )
        texto = '{} ({}) está en pruebas y necesita tu validación.\n' \
                'Si algo falla, repórtalo desde tu portal.'.format(t.code, t.titulo)
        return asunto, envolver('Necesito que lo valides', COLOR_ALERTA, cuerpo,
                                _boton('Ir a mis solicitudes', '/solicitudes',
                                       COLOR_ALERTA)), texto

    if fila.evento == EVENTO_A_PRODUCCION:
        asunto = '[{}] Ya está disponible'.format(t.code)
        cuerpo = (
            '<p>Tu requerimiento <strong>{}</strong> ya quedó disponible en el '
            'sistema. Puedes usarlo desde ahora.</p>'.format(code)
            + tabla_datos([
                ('Requerimiento', titulo),
                ('Entregado el', _fecha_larga(t.fecha_entrega_real)),
            ])
            + '<p>Si más adelante encuentras algo que no funciona, o quieres que '
              'funcione de otra forma, tienes los botones <strong>"Me falla"</strong> y '
              '<strong>"Pedir ajuste"</strong> en tu portal.</p>'
        )
        texto = '{} ({}) ya está disponible en el sistema.'.format(t.code, t.titulo)
        return asunto, envolver('Tu desarrollo ya está listo', COLOR_EXITO, cuerpo,
                                _boton('Ver mis solicitudes', '/solicitudes',
                                       COLOR_EXITO)), texto

    raise ValueError('Evento sin plantilla: {}'.format(fila.evento))


def construir_fallas(filas):
    """Un solo correo con todas las fallas en produccion pendientes de avisar."""
    items = ''
    lineas = []
    for f in filas:
        b, t = f.bug, f.ticket
        if b is None or t is None:
            continue
        items += (
            '<div style="margin:0 0 12px;padding:14px 16px;background:#fdf2f2;'
            'border-left:3px solid {};border-radius:0 8px 8px 0">'
            '<div style="font-size:12px;color:#8b939e">{} · {}</div>'
            '<div style="font-weight:600;font-size:13px;margin:2px 0">{}</div>'
            '<div style="font-size:13px">{}</div></div>'.format(
                COLOR_PELIGRO, _e(t.code), _e(b.reportado_por), _e(t.titulo),
                _e(b.descripcion))
        )
        lineas.append('- {} ({}): {} — {}'.format(
            t.code, t.titulo, b.descripcion, b.reportado_por))

    n = len(lineas)
    plural = 's' if n != 1 else ''
    asunto = '⚠ {} falla{} reportada{} en producción'.format(n, plural, plural)
    cuerpo = (
        '<p>Reportaron {} sobre {} que ya está en producción:</p>{}'.format(
            'fallas' if n != 1 else 'una falla',
            'desarrollos' if n != 1 else 'un desarrollo',
            items)
        + '<p style="font-size:13px;color:#8b939e">Entran a tu bandeja sin severidad. '
          'Clasifícalas para que cuenten en el freno de despliegue.</p>'
    )
    texto = 'Fallas reportadas en producción:\n' + '\n'.join(lineas)
    return asunto, envolver('Falla en producción', COLOR_PELIGRO, cuerpo,
                            _boton('Abrir bandeja', '/dev-tracker', COLOR_PELIGRO)), texto


# ---------------------------------------------------------------------------
# Trabajos del scheduler
# ---------------------------------------------------------------------------

def procesar_cola(app):
    """Envia lo que ya cumplio su ventana de gracia y sigue siendo verdad."""
    with app.app_context():
        try:
            _procesar()
        except Exception as e:
            db.session.rollback()
            log.error('[DevTracker] Error procesando la cola de correos: %s', e)


def _reclamar(fila_id):
    """
    Marca la fila como 'enviando' de forma atomica.

    Si hubiera mas de un worker de gunicorn, los dos correrian este trabajo.
    Solo uno logra el UPDATE y el otro se salta la fila, asi que el correo no
    sale duplicado.
    """
    tocadas = (
        DevEmailOutbox.query
        .filter(DevEmailOutbox.id == fila_id,
                DevEmailOutbox.estado == CORREO_PENDIENTE)
        .update({'estado': CORREO_ENVIANDO}, synchronize_session=False)
    )
    db.session.commit()
    return tocadas == 1


def _procesar():
    vencidas = (
        DevEmailOutbox.query
        .filter(DevEmailOutbox.estado == CORREO_PENDIENTE,
                DevEmailOutbox.programado_para <= ahora_utc())
        .order_by(DevEmailOutbox.id)
        .all()
    )
    if not vencidas:
        return

    fallas, individuales = [], []
    for fila in vencidas:
        if not sigue_vigente(fila):
            fila.estado = CORREO_CANCELADO
            log.info('[DevTracker] Aviso cancelado, el ticket cambió: %s', fila)
            continue
        if not _reclamar(fila.id):
            continue
        if fila.evento == EVENTO_FALLA_PRODUCCION:
            fallas.append(fila)
        else:
            individuales.append(fila)
    db.session.commit()

    for fila in individuales:
        try:
            asunto, cuerpo_html, texto = construir(fila)
            enviar_smtp([fila.destinatario], asunto, cuerpo_html, texto)
            fila.estado = CORREO_ENVIADO
            fila.enviado_en = ahora_utc()
        except Exception as e:
            _marcar_fallo(fila, e)
        db.session.commit()

    # Las fallas se agrupan por destinatario: un correo, no uno por falla.
    por_destinatario = {}
    for fila in fallas:
        por_destinatario.setdefault(fila.destinatario, []).append(fila)

    for destinatario, grupo in por_destinatario.items():
        try:
            asunto, cuerpo_html, texto = construir_fallas(grupo)
            enviar_smtp([destinatario], asunto, cuerpo_html, texto)
            for fila in grupo:
                fila.estado = CORREO_ENVIADO
                fila.enviado_en = ahora_utc()
        except Exception as e:
            for fila in grupo:
                _marcar_fallo(fila, e)
        db.session.commit()


def _marcar_fallo(fila, error):
    fila.intentos += 1
    fila.ultimo_error = str(error)[:500]
    if fila.intentos >= MAX_INTENTOS:
        fila.estado = CORREO_FALLIDO
        log.error('[DevTracker] Correo descartado tras %s intentos: %s', MAX_INTENTOS, fila)
    else:
        # Vuelve a la cola con 15 minutos de espera.
        fila.estado = CORREO_PENDIENTE
        fila.programado_para = ahora_utc() + timedelta(minutes=15)


def enviar_resumen_diario(app):
    """
    Un correo al desarrollador con lo que necesita su atencion.

    Si no hay nada, NO se envia. Un correo que dice "no hay novedades" entrena a
    quien lo recibe a ignorar el remitente.
    """
    with app.app_context():
        try:
            _resumen(app)
        except Exception as e:
            db.session.rollback()
            log.error('[DevTracker] Error en el resumen diario: %s', e)


def _bloque(titulo, color, elementos, render):
    if not elementos:
        return ''
    filas = ''.join(render(x) for x in elementos)
    return (
        '<h2 style="font-size:13px;text-transform:uppercase;letter-spacing:.04em;'
        'color:{};margin:24px 0 10px;font-weight:700">{} ({})</h2>{}'.format(
            color, titulo, len(elementos), filas)
    )


def _linea(t, extra=''):
    return (
        '<div style="padding:10px 14px;margin-bottom:8px;background:#fafbfc;'
        'border-radius:8px;font-size:13px">'
        '<span style="color:#8b939e;font-size:11px">{}</span>'
        '<div style="font-weight:600">{}</div>'
        '<div style="color:#8b939e;font-size:12px">{}{}</div></div>'.format(
            _e(t.code), _e(t.titulo), _e(t.solicitante_nombre or '—'), extra)
    )


def _linea_falla(b):
    return (
        '<div style="padding:10px 14px;margin-bottom:8px;background:#fdf2f2;'
        'border-radius:8px;font-size:13px">'
        '<span style="color:#8b939e;font-size:11px">{}</span>'
        '<div>{}</div>'
        '<div style="color:#8b939e;font-size:12px">{}</div></div>'.format(
            _e(b.ticket.code if b.ticket else ''), _e(b.descripcion), _e(b.reportado_por))
    )


def _texto_vencimiento(t):
    if t.dias_restantes == 0:
        return ' · vence hoy'
    return ' · faltan {} días'.format(t.dias_restantes)


def _resumen(app):
    destinatarios = app.config.get('DEVTRACKER_ADMIN_EMAILS') or []
    destinatarios = [d for d in destinatarios if correos_activos_para(d)]
    if not destinatarios:
        return

    sin_triar = DevTicket.query.filter(DevTicket.estado == ESTADO_POR_REVISAR).all()
    fallas = (DevTicketBug.query
              .filter(DevTicketBug.severidad == SEVERIDAD_SIN_CLASIFICAR,
                      DevTicketBug.estado == 'Abierto').all())
    activos = DevTicket.query.filter(DevTicket.estado.in_(ESTADOS_ACTIVOS)).all()
    retrasados = [t for t in activos if t.estado_plazo == PLAZO_RETRASADO]
    por_vencer = [t for t in activos if t.estado_plazo == PLAZO_POR_VENCER]

    if not (sin_triar or fallas or retrasados or por_vencer):
        log.info('[DevTracker] Resumen diario omitido: no hay novedades.')
        return

    cuerpo = (
        '<p>Esto es lo que necesita tu atención hoy, {}.</p>'.format(
            _fecha_larga(hoy_bogota()))
        + _bloque('Solicitudes por revisar', COLOR_PRIMARIO, sin_triar,
                  lambda t: _linea(t, ' · pidió urgencia {}'.format(
                      _e(t.urgencia_propuesta or 'sin definir'))))
        + _bloque('Fallas sin clasificar', COLOR_PELIGRO, fallas, _linea_falla)
        + _bloque('Retrasados', COLOR_PELIGRO, retrasados,
                  lambda t: _linea(t, ' · {} días de retraso'.format(t.dias_retraso)))
        + _bloque('Vencen pronto', COLOR_ALERTA, por_vencer,
                  lambda t: _linea(t, _texto_vencimiento(t)))
    )

    texto = (
        'Resumen DevTracker\n'
        'Solicitudes por revisar: {}\n'
        'Fallas sin clasificar: {}\n'
        'Retrasados: {}\n'
        'Vencen pronto: {}'.format(
            len(sin_triar), len(fallas), len(retrasados), len(por_vencer))
    )
    asunto = 'DevTracker · {} por revisar, {} retrasado{}'.format(
        len(sin_triar), len(retrasados), 's' if len(retrasados) != 1 else '')

    try:
        enviar_smtp(destinatarios, asunto,
                    envolver('Tu resumen del día', COLOR_PRIMARIO, cuerpo,
                             _boton('Abrir DevTracker', '/dev-tracker')),
                    texto)
    except Exception as e:
        log.error('[DevTracker] No se pudo enviar el resumen diario: %s', e)


def registrar_trabajos(app, scheduler):
    """Engancha los dos trabajos al scheduler que ya corre en app.py."""
    from dev_tracker.tiempo import BOGOTA_TZ

    scheduler.add_job(
        func=lambda: procesar_cola(app),
        trigger='interval', minutes=2,
        id='devtracker_cola_correos', replace_existing=True,
    )
    hora = app.config.get('DEVTRACKER_HORA_RESUMEN', '07:30')
    h, m = (int(x) for x in hora.split(':'))
    scheduler.add_job(
        func=lambda: enviar_resumen_diario(app),
        trigger='cron', hour=h, minute=m, timezone=BOGOTA_TZ,
        id='devtracker_resumen_diario', replace_existing=True,
    )
    log.info('[DevTracker] Correos: cola cada 2 min, resumen diario %s (Bogotá).', hora)

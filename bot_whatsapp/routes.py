# bot_whatsapp/routes.py
from flask import request, jsonify, current_app
from . import bot_bp  # Importamos el blueprint que creamos en __init__.py
# Removemos TODAS las importaciones de app.py que causan circular imports
from datetime import datetime, timedelta
import os
import requests
import re
from apscheduler.jobstores.base import JobLookupError
import spacy
import random

nlp = spacy.load('es_core_news_sm')

VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "TU_TOKEN_SECRETO_INVENTADO")

# Registro de sesiones esperando comando 'NUEVO' tras timeout
AWAITING_NEW_AFTER_TIMEOUT = {}
STEP_TIMER_JOBS = {}

# Paso especial para confirmar reinicio de sesión
STEP_CONFIRM_RESET = 99


def _clear_step_timer_jobs(solicitud_id):
    from app import scheduler  # Importación tardía para evitar ciclos

    jobs = STEP_TIMER_JOBS.pop(solicitud_id, {})
    for job_id in jobs.values():
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass

# Aquí irá el webhook_whatsapp movido


def _schedule_final_timeout_message(solicitud_id, telefono, delay_minutes=10):
    """Programa el mensaje de cierre definitivo si no se recibe 'NUEVO' tras el timeout inicial."""
    from app import scheduler  # Importar en tiempo de ejecución para evitar ciclos

    job_id = f"final_timeout_{solicitud_id}"
    run_at = datetime.utcnow() + timedelta(minutes=delay_minutes)

    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass

    scheduler.add_job(
        func=_send_final_timeout_message,
        trigger='date',
        run_date=run_at,
        args=[solicitud_id, telefono],
        id=job_id,
        replace_existing=True
    )


def _cancel_final_timeout_message(solicitud_id):
    """Cancela el mensaje programado de cierre definitivo si el usuario responde 'NUEVO'."""
    from app import scheduler  # Importar en tiempo de ejecución para evitar ciclos

    job_id = f"final_timeout_{solicitud_id}"
    AWAITING_NEW_AFTER_TIMEOUT.pop(solicitud_id, None)
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def _send_final_timeout_message(solicitud_id, telefono):
    """Mensaje final cuando no se recibe 'NUEVO' dentro del plazo."""
    if solicitud_id not in AWAITING_NEW_AFTER_TIMEOUT:
        return

    from app import app, db, SolicitudCita, send_whatsapp_message, reset_safety_reminder_counter

    with app.app_context():
        solicitud = SolicitudCita.query.get(solicitud_id)
        if not solicitud:
            AWAITING_NEW_AFTER_TIMEOUT.pop(solicitud_id, None)
            return

        mensaje_cierre = (
            "🚪 Fisher 🐶 cierra esta conversación por inactividad."
            " Cuando quieras retomar tu enturnamiento, escribe 'NUEVO'."
            " ¡Te esperamos pronto! 🐾"
        )
        try:
            send_whatsapp_message(telefono, mensaje_cierre)
        except Exception:
            current_app.logger.warning('No se pudo enviar mensaje final de timeout a %s', telefono)
        reset_safety_reminder_counter(telefono)

        solicitud.whatsapp_step = '0'
        solicitud.whatsapp_timeout_minutes = 0
        solicitud.whatsapp_warning_sent = False
        solicitud.whatsapp_last_activity = datetime.utcnow()
        db.session.commit()

        AWAITING_NEW_AFTER_TIMEOUT.pop(solicitud_id, None)


def _send_step_warning_job(solicitud_id, telefono, step_key, message):
    from app import app, db, SolicitudCita, send_whatsapp_message

    with app.app_context():
        solicitud = SolicitudCita.query.get(solicitud_id)
        if not solicitud or str(solicitud.whatsapp_step) != str(step_key):
            return

        try:
            send_whatsapp_message(telefono, message, skip_reminder=True)
        except Exception:
            current_app.logger.warning('No se pudo enviar recordatorio programado a %s', telefono)

        solicitud.whatsapp_warning_sent = True
        solicitud.whatsapp_last_activity = datetime.utcnow()
        db.session.commit()


def _send_step_timeout_job(solicitud_id, telefono, step_key, message, timeout_minutes):
    from app import app, db, SolicitudCita, send_whatsapp_message, reset_safety_reminder_counter

    with app.app_context():
        solicitud = SolicitudCita.query.get(solicitud_id)
        if not solicitud or str(solicitud.whatsapp_step) != str(step_key):
            return

        _clear_step_timer_jobs(solicitud_id)

        final_msg = message or "⏰ Fisher 🐶: tu sesión expiró por inactividad. Escribe 'NUEVO' para reiniciar cuando estés listo."

        try:
            send_whatsapp_message(telefono, final_msg)
        except Exception:
            current_app.logger.warning('No se pudo enviar mensaje de timeout a %s', telefono)

        reset_safety_reminder_counter(telefono)

        solicitud.fecha = datetime.utcnow()
        solicitud.mensaje = final_msg
        solicitud.whatsapp_step = '0'
        solicitud.whatsapp_timeout_minutes = 0
        solicitud.whatsapp_warning_sent = False
        solicitud.whatsapp_last_activity = datetime.utcnow()
        db.session.commit()

        AWAITING_NEW_AFTER_TIMEOUT[solicitud.id] = datetime.utcnow()
        _schedule_final_timeout_message(solicitud.id, telefono)


def schedule_step_timers_for_session(session, telefono):
    solicitud = session.get('solicitud') if session else None
    if not solicitud or not getattr(solicitud, 'id', None):
        return

    from app import scheduler, get_step_timeout_config

    step = session.get('step')
    timeout_cfg = get_step_timeout_config(step)

    _clear_step_timer_jobs(solicitud.id)

    if not timeout_cfg:
        return

    session_timeout = session.get('timeout_minutes') or timeout_cfg.get('timeout')
    timeout_minutes = max(0, session_timeout or 0)
    if timeout_minutes <= 0:
        return

    run_jobs = {}
    now = datetime.utcnow()
    warning_before = timeout_cfg.get('warning_before') or 0
    warning_message = timeout_cfg.get('warning_message')

    if warning_before and warning_message and timeout_minutes > warning_before:
        warn_run = now + timedelta(minutes=timeout_minutes - warning_before)
        if warn_run > now:
            warn_id = f"wh_warning_{solicitud.id}"
            scheduler.add_job(
                func=_send_step_warning_job,
                trigger='date',
                run_date=warn_run,
                args=[solicitud.id, telefono, step, warning_message],
                id=warn_id,
                replace_existing=True
            )
            run_jobs['warning'] = warn_id

    timeout_message = timeout_cfg.get('timeout_message')
    timeout_run = now + timedelta(minutes=timeout_minutes)
    if timeout_run > now:
        timeout_id = f"wh_timeout_{solicitud.id}"
        scheduler.add_job(
            func=_send_step_timeout_job,
            trigger='date',
            run_date=timeout_run,
            args=[solicitud.id, telefono, step, timeout_message, timeout_minutes],
            id=timeout_id,
            replace_existing=True
        )
        run_jobs['timeout'] = timeout_id

    if run_jobs:
        STEP_TIMER_JOBS[solicitud.id] = run_jobs


def _commit_session(telefono, session):
    from app import update_whatsapp_session

    update_whatsapp_session(telefono, session)
    schedule_step_timers_for_session(session, telefono)


def _handle_spoofing_attempt(session, telefono, checkpoint_name):
    """Maneja intentos de spoofing GPS con advertencias progresivas y degradación de prioridad."""
    from app import db, SolicitudCita
    
    solicitud = session.get('solicitud')
    
    # Contar intentos previos desde las observaciones
    spoofing_count = 1  # Este intento actual
    if solicitud and solicitud.observaciones:
        # Contar cuántas marcas de "[SPOOFING #" hay en las observaciones
        import re
        spoofing_matches = re.findall(r'\[SPOOFING #(\d+)\]', solicitud.observaciones)
        if spoofing_matches:
            # El contador más alto encontrado + 1
            spoofing_count = max(int(match) for match in spoofing_matches) + 1
    
    # Mensajes progresivos de Fisher para spoofing
    spoofing_messages = [
        # Primer intento - Divertido pero firme
        f"🐶 Fisher 🐶: ¡Oye, amigo! Detecté que intentaste enviar una ubicación de mapa 📍 en lugar de GPS real desde {checkpoint_name}.\n\n"
        "Sé que eres inteligente, pero esto no engaña a mi nariz de perro 🐕. ¡Inténtalo de nuevo con tu ubicación REAL!",
        
        # Segundo intento - Más serio
        f"🐕 Fisher 🐶: ¡Guau! Segundo intento fallido en {checkpoint_name}. Mi olfato canino huele que estás tratando de engañarme con una ubicación del mapa.\n\n"
        "Recuerda: Clip 📎 → Ubicación → **'Enviar mi ubicación actual'** (el botón azul). ¡No uses el buscador!",
        
        # Tercer intento - Amenazante
        f"🐶 Fisher 🐶: ¡Basta ya! Tres intentos de spoofing GPS en {checkpoint_name}. Mi paciencia de perro se está agotando.\n\n"
        "⚠️ Si sigues intentando engañarme, tu posición en el enturnamiento bajará automáticamente. ¡Envía tu ubicación REAL ahora!",
        
        # Cuarto intento - Muy serio con consecuencias
        f"🐕 Fisher 🐶: ¡Esto es inaceptable! Cuatro intentos de spoofing en {checkpoint_name}.\n\n"
        "🚫 Como castigo por intentar engañar al sistema, tu prioridad en el enturnamiento ha bajado. Ahora tendrás que esperar más tiempo.\n\n"
        "¡Última oportunidad! Envía tu ubicación REAL o tu posición seguirá bajando.",
        
        # Quinto intento y posteriores - Máxima severidad
        f"🐶 Fisher 🐶: ¡Ya basta! Múltiples intentos de spoofing detectados en {checkpoint_name}.\n\n"
        "💀 Tu posición en el enturnamiento ha sido degradada significativamente. Ahora eres el último en la fila.\n\n"
        "Si sigues intentando engañarme, tu solicitud será cancelada permanentemente. ¡Comportate!"
    ]
    
    # Seleccionar mensaje basado en el contador
    # Para intentos > 5, usar siempre el último mensaje (más severo)
    if spoofing_count >= 5:
        message_index = len(spoofing_messages) - 1  # Siempre el último mensaje
    else:
        message_index = min(spoofing_count - 1, len(spoofing_messages) - 1)
    message = spoofing_messages[message_index]
    
    # Degradar prioridad después de ciertos intentos
    if solicitud:
        # Agregar marca de spoofing en las observaciones SIEMPRE
        marca_spoofing = f"[SPOOFING #{spoofing_count}] Intento de ubicación falsa en {checkpoint_name} - {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
        if solicitud.observaciones:
            solicitud.observaciones = f"{solicitud.observaciones}\n{marca_spoofing}"
        else:
            solicitud.observaciones = marca_spoofing
        
        # NO BLOQUEAR NUNCA - Solo registrar el historial
        # El sistema seguirá enviando advertencias hasta que envíe ubicación correcta
        
        db.session.commit()
    
    return message


def _handle_forwarded_ticket_attempt(session, telefono, ticket_type):
    """Maneja intentos de enviar tickets forwarded con advertencias progresivas."""
    from app import db, SolicitudCita
    
    solicitud = session.get('solicitud')
    
    # Contar intentos previos de tickets forwarded desde las observaciones
    ticket_count = 1  # Este intento actual
    if solicitud and solicitud.observaciones:
        # Contar cuántas marcas de "[FORWARDED TICKET #" hay en las observaciones
        import re
        ticket_matches = re.findall(r'\[FORWARDED TICKET #(\d+)\]', solicitud.observaciones)
        if ticket_matches:
            # El contador más alto encontrado + 1
            ticket_count = max(int(match) for match in ticket_matches) + 1
    
    # Mensajes progresivos de Fisher para tickets forwarded
    ticket_messages = [
        # Primer intento - Divertido pero firme
        f"🐶 Fisher 🐶: ¡Oye, amigo! Detecté que intentaste enviar un {ticket_type} 📄 reenviado en lugar de una foto fresca.\n\n"
        "Mi olfato canino huele que esto no es una foto tomada ahora mismo 🐕. ¡Necesito una foto RECIENTE del ticket!",
        
        # Segundo intento - Más serio
        f"🐕 Fisher 🐶: ¡Guau! Segundo intento con {ticket_type} reenviado. Mi nariz está oliendo que estás tratando de engañarme con una foto vieja.\n\n"
        "Recuerda: Abre la cámara 📷 → Toma la foto → **Envíala inmediatamente**. ¡No reenvíes fotos viejas!",
        
        # Tercer intento - Amenazante
        f"🐶 Fisher 🐶: ¡Basta ya! Tres intentos de {ticket_type} reenviado. Mi paciencia de perro se está agotando.\n\n"
        "⚠️ Si sigues enviando fotos reenviadas, tu posición en el enturnamiento bajará automáticamente. ¡Envía una foto FRESCA ahora!",
        
        # Cuarto intento - Muy serio con consecuencias
        f"🐕 Fisher 🐶: ¡Esto es inaceptable! Cuatro intentos de {ticket_type} reenviado.\n\n"
        "🚫 Como castigo por intentar engañar al sistema, tu prioridad en el enturnamiento ha bajado. Ahora tendrás que esperar más tiempo.\n\n"
        "¡Última oportunidad! Envía una foto RECIENTE del ticket o tu posición seguirá bajando.",
        
        # Quinto intento y posteriores - Máxima severidad
        f"🐶 Fisher 🐶: ¡Ya basta! Múltiples intentos de {ticket_type} reenviado detectados.\n\n"
        "💀 Tu posición en el enturnamiento ha sido degradada significativamente. Ahora eres el último en la fila.\n\n"
        "Si sigues enviando fotos reenviadas, tu solicitud será cancelada permanentemente. ¡Comportate!"
    ]
    
    # Seleccionar mensaje basado en el contador
    # Para intentos > 5, usar siempre el último mensaje (más severo)
    if ticket_count >= 5:
        message_index = len(ticket_messages) - 1  # Siempre el último mensaje
    else:
        message_index = min(ticket_count - 1, len(ticket_messages) - 1)
    message = ticket_messages[message_index]
    
    # Registrar el intento en observaciones
    if solicitud:
        # Agregar marca de ticket forwarded en las observaciones SIEMPRE
        marca_ticket = f"[FORWARDED TICKET #{ticket_count}] Intento de {ticket_type} reenviado - {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}"
        if solicitud.observaciones:
            solicitud.observaciones = f"{solicitud.observaciones}\n{marca_ticket}"
        else:
            solicitud.observaciones = marca_ticket
        
        # NO BLOQUEAR NUNCA - Solo registrar el historial
        # El sistema seguirá enviando advertencias hasta que envíe ticket correcto
        
        db.session.commit()
    
    return message


def _send_confirmation_summary(solicitud, telefono):
    """Envía el resumen de confirmación final con todos los datos recopilados."""
    if not solicitud:
        return

    from app import send_yes_no_prompt, build_confirmation_summary

    resumen = build_confirmation_summary(solicitud)
    try:
        send_yes_no_prompt(
            telefono,
            resumen,
            skip_reminder=True,
            context_label='CONF'
        )
    except Exception:
        current_app.logger.warning('No se pudo enviar resumen de confirmación a %s', telefono)


def _prompt_for_next_pending_requirement(session, solicitud, telefono):
    """Determina el siguiente requisito pendiente y envía la petición apropiada."""
    if not solicitud:
        return

    from app import (
        determinar_siguiente_step_pendiente,
        send_whatsapp_message,
        configurar_timeout_session,
        enviar_mensaje_solicitar_ubicacion,
        reset_contextual_memory,
        STEP_AWAIT_GUIA,
        STEP_AWAIT_MANIFIESTO,
        STEP_AWAIT_GPS_BOSCONIA,
        STEP_AWAIT_TICKET_GAMBOTE,
        STEP_AWAIT_GPS_GAMBOTE,
        STEP_FINAL_CONFIRMATION
    )

    # Constantes de tiempo logístico
    TIMEOUT_DOCUMENTOS = 60  # 1 hora para documentos
    TIMEOUT_VIAJE_LARGO = 4320  # 72 horas / 3 días para viajes largos
    TIMEOUT_ANTI_FRAUDE = 30  # 30 minutos para anti-fraude GPS

    siguiente = determinar_siguiente_step_pendiente(solicitud)

    reset_contextual_memory(session)

    if siguiente == STEP_AWAIT_GUIA:
        session['step'] = STEP_AWAIT_GUIA
        configurar_timeout_session(session, TIMEOUT_DOCUMENTOS)
        try:
            send_whatsapp_message(telefono, "🐶 Fisher 🐶: ¡Woof! Es hora de la guía. Envía la foto o PDF de tu guía de transporte. Mi nariz de perro detective revisará cada línea para que tu viaje sea impecable. ¡Vamos, no me dejes con la lengua afuera esperando!")
        except Exception:
            current_app.logger.warning('No se pudo solicitar guía nuevamente a %s', telefono)
    elif siguiente == STEP_AWAIT_MANIFIESTO:
        session['step'] = STEP_AWAIT_MANIFIESTO
        configurar_timeout_session(session, TIMEOUT_DOCUMENTOS)
        try:
            send_whatsapp_message(telefono, "🐶 Fisher 🐶: ¡Guía recibida! Ahora necesito el manifiesto como imagen o PDF. Mi nariz está ansiosa por revisar todos los documentos. ¡Envíalo pronto para continuar con tu enturne!")
        except Exception:
            current_app.logger.warning('No se pudo solicitar manifiesto a %s', telefono)
    elif siguiente == STEP_AWAIT_GPS_BOSCONIA:
        session['step'] = STEP_AWAIT_GPS_BOSCONIA
        configurar_timeout_session(session, TIMEOUT_VIAJE_LARGO)
        try:
            send_whatsapp_message(telefono, "📍 ¡Punto de control: Bosconia! 🚛\n\nPara verificar que estás en ruta, envíame tu Ubicación en Tiempo Real desde Bosconia (Clip 📎 -> Ubicación -> Tiempo Real).\n\n🐶 Fisher está vigilando el camino. ¡No intentes engañarme con ubicaciones del mapa o reenviadas, mi olfato es infalible!")
        except Exception:
            current_app.logger.warning('No se pudo solicitar ubicación de Bosconia a %s', telefono)
    elif siguiente == STEP_AWAIT_TICKET_GAMBOTE:
        session['step'] = STEP_AWAIT_TICKET_GAMBOTE
        configurar_timeout_session(session, TIMEOUT_VIAJE_LARGO)
        try:
            send_whatsapp_message(telefono, "🎫 ¡Próxima parada: Gambote! 🚚\n\nCuando pases el peaje, envíame una foto clara del ticket.\n\n⚠️ ¡Atento, amigo! Apenas reciba el ticket, mi nariz de sabueso te pedirá tu Ubicación en Tiempo Real de inmediato. Ve buscando un lugar seguro y con señal, ¡no me hagas esperar mucho o me pongo nervioso! 🐾")
        except Exception:
            current_app.logger.warning('No se pudo solicitar ticket de Gambote a %s', telefono)
    elif siguiente == STEP_AWAIT_GPS_GAMBOTE:
        session['step'] = STEP_AWAIT_GPS_GAMBOTE
        configurar_timeout_session(session, TIMEOUT_ANTI_FRAUDE)
        try:
            send_whatsapp_message(telefono, "📍 ¡Olfateando rastro! 🐶\n\nYa tengo el ticket. Para confirmar que estás ahí físicamente, envíame tu Ubicación en Tiempo Real YA MISMO (Clip 📎 -> Ubicación -> Tiempo Real).\n\n⏳ Tienes 30 minutos exactos. Si no la envías antes de que se acabe el tiempo, tendré que anular el turno por seguridad. ¡Corre!")
        except Exception:
            current_app.logger.warning('No se pudo solicitar ubicación de Gambote a %s', telefono)
    elif siguiente == STEP_FINAL_CONFIRMATION:
        session['step'] = STEP_FINAL_CONFIRMATION
        configurar_timeout_session(session, None)
        _send_confirmation_summary(solicitud, telefono)

@bot_bp.route('/webhook/whatsapp', methods=['GET', 'POST'])
def webhook_whatsapp():
    # Importaciones locales para evitar circular imports
    from app import (
    app, db, SolicitudCita,
        send_whatsapp_message,
        send_yes_no_prompt,
        get_or_create_whatsapp_session,
        log_whatsapp_message,
        is_confirmation_negative,
        is_confirmation_positive,
        buscar_conductor_por_placa,
        guardar_imagen_whatsapp,
        validar_y_guardar_ubicacion,
        enviar_mensaje_solicitar_ubicacion,
        configurar_timeout_session,
        get_solicitud_data,
            get_step_timeout_config,
        compose_contextual_hint,
        reset_contextual_memory,
        reset_safety_reminder_counter,
        STEP_HANDLERS,
        STEP_INACTIVE,
        STEP_WELCOME,
        STEP_AWAIT_PLACA,
        STEP_CONFIRM_DATA,
        STEP_AWAIT_GUIA,
        STEP_AWAIT_GPS_BOSCONIA,
        STEP_AWAIT_TICKET_GAMBOTE,
        STEP_AWAIT_GPS_GAMBOTE,
        STEP_FINAL_CONFIRMATION,
        STEP_MANUAL_REG_NAME,
        STEP_MANUAL_REG_CEDULA,
        STEP_MANUAL_REG_REMOLQUE,
        STEP_MANUAL_REG_CONFIRM,
    STEP_CONFIRM_UNKNOWN_PLACA,
        STEP_UNDER_REVIEW,
        STEP_HUMAN_HANDOFF,
        STATE_PENDING_INSCRIPTION,
        handle_step_welcome,
        handle_step_await_placa,
    )
    
    # Ensure we have application context for database operations
    with app.app_context():
        return _webhook_whatsapp_impl()

def _webhook_whatsapp_impl():
    # Importaciones locales para evitar circular imports
    from app import (
    db, SolicitudCita,
        send_whatsapp_message,
        send_yes_no_prompt,
        get_or_create_whatsapp_session,
        log_whatsapp_message,
        is_confirmation_negative,
        is_confirmation_positive,
        buscar_conductor_por_placa,
        guardar_imagen_whatsapp,
        validar_y_guardar_ubicacion,
        enviar_mensaje_solicitar_ubicacion,
        configurar_timeout_session,
        get_solicitud_data,
    get_step_timeout_config,
        compose_contextual_hint,
        reset_contextual_memory,
        reset_safety_reminder_counter,
        STEP_HANDLERS,
        STEP_INACTIVE,
        STEP_WELCOME,
        STEP_AWAIT_PLACA,
        STEP_CONFIRM_DATA,
        STEP_AWAIT_GUIA,
        STEP_AWAIT_MANIFIESTO,
        STEP_AWAIT_GPS_BOSCONIA,
        STEP_AWAIT_TICKET_GAMBOTE,
        STEP_AWAIT_GPS_GAMBOTE,
        STEP_FINAL_CONFIRMATION,
        STEP_MANUAL_REG_NAME,
        STEP_MANUAL_REG_CEDULA,
        STEP_MANUAL_REG_REMOLQUE,
        STEP_MANUAL_REG_CONFIRM,
    STEP_CONFIRM_UNKNOWN_PLACA,
        STEP_UNDER_REVIEW,
        STEP_HUMAN_HANDOFF,
        STATE_PENDING_INSCRIPTION,
        handle_step_welcome,
        handle_step_await_placa,
    )
    
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                print('WEBHOOK_VERIFIED')
                return challenge, 200
            else:
                print('WEBHOOK_VERIFICATION_FAILED - Wrong token')
                return 'Forbidden', 403
        else:
            print('WEBHOOK_VERIFICATION_FAILED - Missing parameters')
            return 'Bad Request', 400
    if request.method == 'POST':
        # --- FLUJO CONVERSACIONAL PASO A PASO ---
        # Las sesiones ahora se manejan desde la base de datos
        data = request.get_json()
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])
        if not messages:
            return 'ok', 200
        msg = messages[0]
        telefono = msg['from']
        tipo_original = msg.get('type')
        tipo = tipo_original
        texto = msg.get('text', {}).get('body', '').strip()
        interactive_reply = None

        if tipo_original == 'interactive':
            interactive_data = msg.get('interactive') or {}
            interactive_reply = interactive_data.get('button_reply') or interactive_data.get('list_reply') or {}
            texto = (interactive_reply.get('title') or interactive_reply.get('id') or '').strip()
            if not texto:
                reply_id = (interactive_reply.get('id') or '').upper()
                if reply_id.startswith('YES'):
                    texto = 'Sí'
                elif reply_id.startswith('NO'):
                    texto = 'No'
            tipo = 'text'
        # Estado conversacional: por teléfono (desde base de datos)
        session = get_or_create_whatsapp_session(telefono)
        step = session['step']
        user_data = session['data']

        current_step_key = str(step)
        if session.get('_last_step_seen') != current_step_key:
            session['_last_step_seen'] = current_step_key
            reset_contextual_memory(session)

        texto_normalizado = (texto or '').strip().lower()

        if texto_normalizado and 'asesor' in texto_normalizado and step != STEP_HUMAN_HANDOFF:
            try:
                log_whatsapp_message(
                    telefono,
                    texto or '',
                    direction='inbound',
                    sender='driver',
                    message_type=tipo_original or 'text',
                    solicitud=session.get('solicitud')
                )
            except Exception:
                current_app.logger.warning('No se pudo registrar mensaje de asesor para %s', telefono)
            send_whatsapp_message(
                telefono,
                "Entendido. Avisaré a un asesor humano para que continúe contigo en breve.",
                skip_reminder=True
            )
            reset_contextual_memory(session)
            session['step'] = STEP_HUMAN_HANDOFF
            configurar_timeout_session(session, None)
            solicitud_escalada = session.get('solicitud')
            if solicitud_escalada:
                solicitud_escalada.asesor_pendiente = True
                if not solicitud_escalada.asesor_pendiente_desde:
                    solicitud_escalada.asesor_pendiente_desde = datetime.utcnow()
                solicitud_escalada.whatsapp_step = str(STEP_HUMAN_HANDOFF)
                solicitud_escalada.whatsapp_last_activity = datetime.utcnow()
                solicitud_escalada.whatsapp_warning_sent = False
                db.session.commit()
            _commit_session(telefono, session)
            return 'ok', 200

        # Manejar comandos especiales
        if texto_normalizado in ['ayuda', 'help', 'comandos']:
            ayuda_msg = (
                "🐶 Fisher 🐶 comandos disponibles:\n"
                "- 'estado' o 'status': Ver el estado de tu solicitud\n"
                "- 'ayuda' o 'help': Ver esta ayuda\n"
                "- 'asesor': Pedir ayuda humana\n"
                "- 'nuevo' o 'reiniciar': Reiniciar el proceso\n"
                "Si tienes preguntas, escribe 'asesor'."
            )
            send_whatsapp_message(telefono, ayuda_msg, skip_reminder=True)
            _commit_session(telefono, session)
            return 'ok', 200
        elif texto_normalizado in ['estado', 'status', 'mi estado']:
            step = session.get('step', 0)
            step_names = {
                0: "Inicio",
                1: "Bienvenida",
                2: "Esperando placa",
                3: "Confirmando datos",
                4: "Esperando guía",
                15: "Esperando manifiesto",
                5: "Esperando ubicación Bosconia",
                6: "Esperando ticket Gambote",
                7: "Esperando ubicación Gambote",
                9: "Confirmación final",
                'confirmed': "Confirmado, esperando turno",
                STEP_HUMAN_HANDOFF: "En manos de asesor humano"
            }
            estado_msg = f"🐶 Tu estado actual: {step_names.get(step, 'Desconocido')}"
            solicitud = session.get('solicitud')
            if solicitud:
                estado_msg += f"\nEstado solicitud: {solicitud.estado}"
                if solicitud.turno:
                    estado_msg += f"\nTurno asignado: {solicitud.turno}"
            send_whatsapp_message(telefono, estado_msg, skip_reminder=True)
            _commit_session(telefono, session)
            return 'ok', 200

        # Registrar mensaje entrante para que el equipo humano pueda consultarlo.
        try:
            solicitud_para_log = session.get('solicitud')
            contenido_log = texto or ''
            media_ref = None

            if tipo_original == 'location':
                loc = msg.get('location', {})
                lat = loc.get('latitude')
                lng = loc.get('longitude')
                contenido_log = f"Ubicación enviada: lat={lat}, lng={lng}"
            elif tipo_original == 'image':
                media = msg.get('image', {})
                media_ref = media.get('id') or media.get('link')
                contenido_log = media.get('caption') or 'Imagen recibida'
            elif tipo_original == 'document':
                media = msg.get('document', {})
                media_ref = media.get('id') or media.get('link')
                contenido_log = media.get('filename') or 'Documento recibido'
            elif tipo_original == 'interactive':
                respuesta_id = interactive_reply.get('id') if interactive_reply else ''
                if not contenido_log:
                    contenido_log = f"Respuesta rápida seleccionada ({respuesta_id})"
            elif tipo_original and not contenido_log:
                contenido_log = f"Mensaje tipo {tipo_original} recibido"

            log_whatsapp_message(
                telefono,
                contenido_log,
                direction='inbound',
                sender='driver',
                message_type=tipo_original or 'text',
                media_url=media_ref,
                solicitud=solicitud_para_log
            )
        except Exception:
            current_app.logger.debug('No se pudo registrar mensaje entrante para %s', telefono)

        # Verificar timeout específico por paso
        last_activity = session.get('last_activity', datetime.now())
        timeout_minutes = session.get('timeout_minutes')
        step_config = get_step_timeout_config(step)
        warning_before = step_config.get('warning_before') or 0
        timeout_message = step_config.get('timeout_message')

        if step != STEP_HUMAN_HANDOFF and timeout_minutes:
            tiempo_transcurrido_min = (datetime.now() - last_activity).total_seconds() / 60
            if tiempo_transcurrido_min > timeout_minutes:
                # Timeout expirado: reiniciar flujo automáticamente
                solicitud_timeout = session.get('solicitud')
                if solicitud_timeout:
                    solicitud_timeout.fecha = datetime.utcnow()
                    if timeout_message:
                        solicitud_timeout.mensaje = timeout_message
                    else:
                        solicitud_timeout.mensaje = 'Sesión reiniciada por timeout'
                    db.session.commit()
                    AWAITING_NEW_AFTER_TIMEOUT[solicitud_timeout.id] = datetime.utcnow()
                    _schedule_final_timeout_message(solicitud_timeout.id, telefono)
                session['step'] = 0
                session['data'] = {}
                configurar_timeout_session(session, None)
                session['last_activity'] = datetime.now()
                _commit_session(telefono, session)
                final_msg = timeout_message or "⏰ Fisher 🐶: tu sesión expiró por inactividad. Escribe 'NUEVO' para reiniciar cuando estés listo."
                send_whatsapp_message(telefono, final_msg)
                return 'ok', 200

        # Actualizar timestamp de última actividad
        session['last_activity'] = datetime.now()
        # Resetear warning_sent cuando responde
        session['warning_sent'] = False

        # Manejar cancelación en cualquier momento, excepto en pasos donde 'no' es parte del flujo
        protected_no_steps = {
            STEP_WELCOME,
            STEP_CONFIRM_DATA,
            STEP_FINAL_CONFIRMATION,
            STEP_MANUAL_REG_NAME,
            STEP_MANUAL_REG_CEDULA,
            STEP_MANUAL_REG_REMOLQUE,
            STEP_MANUAL_REG_CONFIRM,
            STEP_CONFIRM_UNKNOWN_PLACA,
            STEP_HUMAN_HANDOFF,
            STEP_CONFIRM_RESET
        }
        if texto.upper() == 'NO' and step not in protected_no_steps:
            send_whatsapp_message(
                telefono,
                "Fisher 🐶 entiende la señal y guarda tu solicitud por ahora. Si necesitas retomarla, solo escribe 'NUEVO' y volvemos a rodar juntos."
            )
            reset_safety_reminder_counter(telefono)
            reset_contextual_memory(session)
            # Limpiar la sesión en la base de datos
            solicitud_cancel = session.get('solicitud')
            if solicitud_cancel:
                _cancel_final_timeout_message(solicitud_cancel.id)
            session['step'] = 0
            session['data'] = {}
            _commit_session(telefono, session)
            return 'ok', 200

        # Si el usuario escribe 'NUEVO' o 'REINICIAR', verificar si hay datos valiosos antes de reiniciar
        if texto.upper() in ['NUEVO', 'REINICIAR', 'RESET', 'INICIAR']:
            solicitud_reset = session.get('solicitud')
            if not solicitud_reset:
                solicitud_reset = (
                    SolicitudCita.query
                    .filter_by(telefono=telefono)
                    .order_by(SolicitudCita.fecha.desc())
                    .first()
                )

            # Verificar si hay datos valiosos (imagen_guia o paso_bosconia)
            tiene_datos_valiosos = False
            if solicitud_reset and (solicitud_reset.imagen_guia or solicitud_reset.paso_bosconia):
                tiene_datos_valiosos = True

            if tiene_datos_valiosos:
                # Paso intermedio de confirmación
                session['step'] = STEP_CONFIRM_RESET
                _commit_session(telefono, session)
                advertencia = (
                    "🐶 ¡Espera! Tienes un viaje activo. Si escribes 'NUEVO' se borrarán todos tus datos y perderás tu turno. "
                    "¿Estás seguro? Responde SÍ para borrar todo o NO para continuar tu viaje."
                )
                send_yes_no_prompt(
                    telefono,
                    advertencia,
                    skip_reminder=True,
                    prime_after_force=True,
                    context_label='CONFIRMAR_RESET'
                )
                return 'ok', 200

            # Si no hay datos valiosos, proceder con el reinicio original
            from app import _normalize_timeout_minutes
            timeout_restart = _normalize_timeout_minutes(15)

            if solicitud_reset:
                _cancel_final_timeout_message(solicitud_reset.id)
                solicitud_reset.mensaje = 'Sesión reiniciada por el usuario'
                solicitud_reset.fecha = datetime.utcnow()
                solicitud_reset.estado = 'preconfirmacion'
                solicitud_reset.turno = None
                solicitud_reset.fecha_descargue = None
                solicitud_reset.lugar_descargue = None
                solicitud_reset.observaciones = None
                solicitud_reset.nombre_completo = None
                solicitud_reset.cedula = None
                solicitud_reset.placa = None
                solicitud_reset.placa_remolque = None
                solicitud_reset.celular = None
                solicitud_reset.imagen_guia = None
                solicitud_reset.imagen_manifiesto = None
                solicitud_reset.paso_bosconia = False
                solicitud_reset.ticket_gambote = None
                solicitud_reset.ubicacion_lat = None
                solicitud_reset.ubicacion_lng = None
                solicitud_reset.ubicacion_gambote_lat = None
                solicitud_reset.ubicacion_gambote_lng = None
                solicitud_reset.paso_gambote = False
                solicitud_reset.ubicacion_zisa_lat = None
                solicitud_reset.ubicacion_zisa_lng = None
                solicitud_reset.paso_zisa = False
                solicitud_reset.whatsapp_step = '0'
                solicitud_reset.whatsapp_timeout_minutes = timeout_restart
                solicitud_reset.whatsapp_warning_sent = False
                solicitud_reset.whatsapp_last_activity = datetime.utcnow()
                solicitud_reset.asesor_pendiente = False
                solicitud_reset.asesor_pendiente_desde = None
                db.session.commit()
            else:
                solicitud_reset = SolicitudCita(
                    telefono=telefono,
                    mensaje='Sesión reiniciada por el usuario',
                    estado='preconfirmacion',
                    fecha=datetime.utcnow(),
                    whatsapp_step='0',
                    whatsapp_timeout_minutes=timeout_restart,
                    whatsapp_warning_sent=False,
                    asesor_pendiente=False
                )
                db.session.add(solicitud_reset)
                db.session.commit()

            reset_safety_reminder_counter(telefono)
            reset_contextual_memory(session)
            session = {
                'step': 0,
                'data': {},
                'last_activity': datetime.now(),
                'timeout_minutes': timeout_restart,
                'warning_sent': False,
                'solicitud': solicitud_reset,
                'welcome_invalid_attempts': 0
            }
            _commit_session(telefono, session)
            mensaje_reinicio = (
                "¡Hola! Soy Fisher 🐶, tu asistente en Conquers.\n"
                "Te doy la bienvenida a nuestro WhatsApp.\n"
                "¿Vienes a gestionar tu enturne?"
            )
            send_yes_no_prompt(
                telefono,
                mensaje_reinicio,
                skip_reminder=True,
                prime_after_force=True,
                context_label='REINICIO'
            )
            session['step'] = 1
            session['last_activity'] = datetime.now()
            session['welcome_invalid_attempts'] = 0
            _commit_session(telefono, session)
            return 'ok', 200
        # Si estamos esperando 'NUEVO' después de un timeout, bloquear cualquier otro mensaje
        solicitud_actual = session.get('solicitud')
        if solicitud_actual and solicitud_actual.id in AWAITING_NEW_AFTER_TIMEOUT:
            send_whatsapp_message(telefono, "Fisher 🐶 sigue atento. Para retomar el proceso escribe 'NUEVO'. Cuando quieras volver, aquí estaré.")
            _commit_session(telefono, session)
            return 'ok', 200
        # Continuar con el flujo conversacional usando la sesión de la base de datos
        step = session['step']
        user_data = session['data']

        # Handler para confirmación de reinicio (STEP_CONFIRM_RESET)
        if step == STEP_CONFIRM_RESET:
            respuesta = texto.strip().upper()
            solicitud_reset = session.get('solicitud')
            from app import _normalize_timeout_minutes, determinar_siguiente_step_pendiente
            if respuesta in ['SI', 'SÍ', 'YES']:
                timeout_restart = _normalize_timeout_minutes(15)
                if solicitud_reset:
                    _cancel_final_timeout_message(solicitud_reset.id)
                    solicitud_reset.mensaje = 'Sesión reiniciada por el usuario'
                    solicitud_reset.fecha = datetime.utcnow()
                    solicitud_reset.estado = 'preconfirmacion'
                    solicitud_reset.turno = None
                    solicitud_reset.fecha_descargue = None
                    solicitud_reset.lugar_descargue = None
                    solicitud_reset.observaciones = None
                    solicitud_reset.nombre_completo = None
                    solicitud_reset.cedula = None
                    solicitud_reset.placa = None
                    solicitud_reset.placa_remolque = None
                    solicitud_reset.celular = None
                    solicitud_reset.imagen_guia = None
                    solicitud_reset.imagen_manifiesto = None
                    solicitud_reset.paso_bosconia = False
                    solicitud_reset.ticket_gambote = None
                    solicitud_reset.ubicacion_lat = None
                    solicitud_reset.ubicacion_lng = None
                    solicitud_reset.ubicacion_gambote_lat = None
                    solicitud_reset.ubicacion_gambote_lng = None
                    solicitud_reset.paso_gambote = False
                    solicitud_reset.ubicacion_zisa_lat = None
                    solicitud_reset.ubicacion_zisa_lng = None
                    solicitud_reset.paso_zisa = False
                    solicitud_reset.whatsapp_step = '0'
                    solicitud_reset.whatsapp_timeout_minutes = timeout_restart
                    solicitud_reset.whatsapp_warning_sent = False
                    solicitud_reset.whatsapp_last_activity = datetime.utcnow()
                    solicitud_reset.asesor_pendiente = False
                    solicitud_reset.asesor_pendiente_desde = None
                    db.session.commit()
                else:
                    solicitud_reset = SolicitudCita(
                        telefono=telefono,
                        mensaje='Sesión reiniciada por el usuario',
                        estado='preconfirmacion',
                        fecha=datetime.utcnow(),
                        whatsapp_step='0',
                        whatsapp_timeout_minutes=timeout_restart,
                        whatsapp_warning_sent=False,
                        asesor_pendiente=False
                    )
                    db.session.add(solicitud_reset)
                    db.session.commit()

                reset_safety_reminder_counter(telefono)
                reset_contextual_memory(session)
                session = {
                    'step': 0,
                    'data': {},
                    'last_activity': datetime.now(),
                    'timeout_minutes': timeout_restart,
                    'warning_sent': False,
                    'solicitud': solicitud_reset,
                    'welcome_invalid_attempts': 0
                }
                _commit_session(telefono, session)
                mensaje_reinicio = (
                    "¡Hola! Soy Fisher 🐶, tu asistente en Conquers.\n"
                    "Te doy la bienvenida a nuestro WhatsApp.\n"
                    "¿Vienes a gestionar tu enturne?"
                )
                send_yes_no_prompt(
                    telefono,
                    mensaje_reinicio,
                    skip_reminder=True,
                    prime_after_force=True,
                    context_label='REINICIO'
                )
                session['step'] = 1
                session['last_activity'] = datetime.now()
                session['welcome_invalid_attempts'] = 0
                _commit_session(telefono, session)
                return 'ok', 200
            elif respuesta in ['NO', 'N', 'CANCELAR', 'CONTINUAR']:
                # Restaurar el estado anterior y retomar el flujo
                if solicitud_reset:
                    # Determinar el siguiente paso pendiente
                    siguiente_step = determinar_siguiente_step_pendiente(solicitud_reset)
                    session['step'] = siguiente_step
                    _commit_session(telefono, session)
                    send_whatsapp_message(telefono, "✅ Uff, ¡casi! Sigamos con tu viaje donde lo dejamos.")
                    # Opcional: disparar el prompt del siguiente pendiente
                    _prompt_for_next_pending_requirement(session, solicitud_reset, telefono)
                    return 'ok', 200
                else:
                    # Si no hay solicitud, simplemente volver a bienvenida
                    session['step'] = 0
                    _commit_session(telefono, session)
                    send_whatsapp_message(telefono, "No encontré un viaje activo. Si quieres iniciar uno nuevo, escribe 'NUEVO'.")
                    return 'ok', 200
            else:
                # Respuesta no reconocida
                send_whatsapp_message(telefono, "Por favor responde SÍ para reiniciar o NO para continuar tu viaje.")
                return 'ok', 200

        if step == STEP_HUMAN_HANDOFF:
            solicitud_handoff = session.get('solicitud')
            if solicitud_handoff and getattr(solicitud_handoff, 'asesor_pendiente', False):
                ahora = datetime.utcnow()
                tiempo_asesor_pendiente = getattr(solicitud_handoff, 'asesor_pendiente_desde', None)
                
                # Enviar mensajes automáticos de espera basados en tiempo transcurrido
                if tiempo_asesor_pendiente:
                    minutos_transcurridos = (ahora - tiempo_asesor_pendiente).total_seconds() / 60
                    mensajes_automaticos_enviados = session.get('auto_wait_messages_sent', 0)
                    
                    # Definir intervalos para mensajes automáticos (en minutos)
                    intervalos_mensajes = [5, 15, 30, 60, 120]  # 5min, 15min, 30min, 1hora, 2horas
                    
                    if mensajes_automaticos_enviados < len(intervalos_mensajes) and minutos_transcurridos >= intervalos_mensajes[mensajes_automaticos_enviados]:
                        # Mensajes automáticos de espera con Fisher
                        mensajes_espera = [
                            "🐶 Fisher 🐶: ¡Guau! Mi cola se mueve esperando al equipo humano. Pronto te darán noticias de tu turno. ¡Paciencia, amigo!",
                            "🐕 Fisher 🐶: Estoy ladrando fuerte para llamar al asesor. Tu caso está siendo revisado con prioridad. ¡Un poco más de espera!",
                            "🐶 Fisher 🐶: Mi hocico está ocupado transmitiendo tu mensaje al equipo. Están trabajando duro en tu solicitud. ¡Pronto tendrás respuesta!",
                            "🐕 Fisher 🐶: ¡Estoy corriendo en círculos para acelerar el proceso! El equipo humano está en ello. Gracias por tu paciencia.",
                            "🐶 Fisher 🐶: Mi corazón de perro late fuerte esperando al asesor. Tu turno está siendo ajustado. ¡Ya casi terminamos!"
                        ]
                        
                        if mensajes_automaticos_enviados < len(mensajes_espera):
                            mensaje_auto = mensajes_espera[mensajes_automaticos_enviados]
                            try:
                                send_whatsapp_message(telefono, mensaje_auto, skip_reminder=True)
                                session['auto_wait_messages_sent'] = mensajes_automaticos_enviados + 1
                                solicitud_handoff.whatsapp_last_activity = ahora
                                db.session.commit()
                                current_app.logger.info(f'Mensaje automático de espera enviado a {telefono} (mensaje #{mensajes_automaticos_enviados + 1})')
                            except Exception:
                                current_app.logger.warning('No se pudo enviar mensaje automático de espera para solicitud %s', solicitud_handoff.id)
                
                # Initialize warning count if not present
                warning_count = session.get('warning_count', 0)
                
                # Process incoming message with NLP if text is provided and doesn't contain 'asesor'
                if texto and 'asesor' not in texto.lower():
                    # Siempre responder algo al conductor para mantenerlo informado
                    ahora = datetime.utcnow()
                    tiempo_asesor_pendiente = getattr(solicitud_handoff, 'asesor_pendiente_desde', None)
                    minutos_esperando = 0
                    if tiempo_asesor_pendiente:
                        minutos_esperando = (ahora - tiempo_asesor_pendiente).total_seconds() / 60
                    
                    # Mensajes de Fisher para mantener la conversación activa
                    mensajes_paciencia_fisher = [
                        "🐶 Fisher 🐶: ¡Estoy aquí vigilando! Mi cola se mueve cada vez que veo que escribes. El equipo humano está trabajando en tu caso. ¡Un poquito más de paciencia!",
                        "🐕 Fisher 🐶: ¡Guau! Veo que sigues atento. Estoy ladrando fuerte para recordarle al equipo que tienes prisa. Pronto tendrás noticias. ¡Buen chico!",
                        "🐶 Fisher 🐶: Mi hocico está ocupado transmitiendo todos tus mensajes al equipo. Están revisando tu solicitud con prioridad. ¡Gracias por esperar!",
                        "🐕 Fisher 🐶: ¡Estoy corriendo en círculos para llamar la atención del humano! Tu caso está siendo atendido. Mantén la calma, amigo.",
                        "🐶 Fisher 🐶: ¡Mi corazón late fuerte por ti! Cada mensaje tuyo es como una caricia en mi cabeza. El asesor llegará pronto con buenas noticias.",
                        "🐕 Fisher 🐶: Estoy moviendo la cola de felicidad porque sigues aquí. Significa que confías en nosotros. ¡El equipo está en ello!",
                        "🐶 Fisher 🐶: ¡Qué perseverancia la tuya! Estoy ladrando sin parar para que el humano te responda. Tu paciencia será recompensada.",
                        "🐕 Fisher 🐶: Mi nariz está olfateando el aire esperando al asesor. Cada minuto que pasa estamos más cerca de resolver tu caso. ¡Ánimo!"
                    ]
                    
                    # Seleccionar mensaje basado en tiempo de espera
                    if minutos_esperando > 60:  # Más de 1 hora
                        mensaje_respuesta = random.choice(mensajes_paciencia_fisher[-4:])  # Mensajes más motivadores
                    elif minutos_esperando > 30:  # Más de 30 min
                        mensaje_respuesta = random.choice(mensajes_paciencia_fisher[-6:])  # Mensajes intermedios
                    else:  # Menos de 30 min
                        mensaje_respuesta = random.choice(mensajes_paciencia_fisher[:4])  # Mensajes iniciales
                    
                    try:
                        send_whatsapp_message(telefono, mensaje_respuesta, skip_reminder=True)
                        solicitud_handoff.whatsapp_last_activity = ahora
                        db.session.commit()
                    except Exception:
                        current_app.logger.warning('No se pudo enviar mensaje de paciencia para solicitud %s', solicitud_handoff.id)
                else:
                    # Original logic: send initial warning if not sent
                    if not getattr(solicitud_handoff, 'whatsapp_warning_sent', False):
                        aviso = (
                            "👋 Nuestro equipo humano sigue gestionando el ajuste de tu turno por la operación. "
                            "Apenas tengamos confirmada la nueva fecha, hora y número de turno te avisaremos por este chat. "
                            "Gracias por tu paciencia."
                        )
                        try:
                            send_whatsapp_message(telefono, aviso, skip_reminder=True)
                        except Exception:
                            current_app.logger.warning('No se pudo enviar aviso de espera para solicitud %s', solicitud_handoff.id)
                        else:
                            solicitud_handoff.whatsapp_warning_sent = True
                            solicitud_handoff.whatsapp_last_activity = datetime.utcnow()
                            try:
                                db.session.commit()
                            except Exception:
                                db.session.rollback()
                                current_app.logger.exception('No se pudo persistir aviso de espera para solicitud %s', solicitud_handoff.id)
            
            session['last_activity'] = datetime.now()
            _commit_session(telefono, session)
            return 'ok', 200
        
        # Usar handlers para estados refactorizados, fallback al if/elif legacy
        handler = STEP_HANDLERS.get(step)
        if handler:
            result = handler(telefono, texto, tipo, msg, session)
            _commit_session(telefono, session)
            if result:  # Si el handler retorna algo (como 'ok', 200), devolverlo
                return result
            # Si retorna None, continuar con el flujo normal
            return 'ok', 200
        
        # Flujo legacy con if/elif para estados no refactorizados aún
        if step == 0:
            reset_safety_reminder_counter(telefono)
            mensaje_bienvenida = (
                "¡Hola! Soy Fisher 🐶, tu asistente en Conquers.\n"
                "Te doy la bienvenida a nuestro WhatsApp.\n"
                "¿Vienes a gestionar tu enturne?"
            )
            send_yes_no_prompt(
                telefono,
                mensaje_bienvenida,
                skip_reminder=True,
                prime_after_force=True,
                context_label='WELCOME'
            )
            session['step'] = 1
            session['welcome_invalid_attempts'] = 0
        elif step == 1:
            texto_lower = (texto or '').strip().lower()
            if 'asesor' in texto_lower:
                send_whatsapp_message(
                    telefono,
                    "Entendido. Avisaré a un asesor humano para que continúe contigo en breve.",
                    skip_reminder=True
                )
                reset_contextual_memory(session)
                session['step'] = STEP_HUMAN_HANDOFF
                configurar_timeout_session(session, 60)
                session['welcome_invalid_attempts'] = 0

                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.asesor_pendiente = True
                    if not solicitud.asesor_pendiente_desde:
                        solicitud.asesor_pendiente_desde = datetime.utcnow()
                    solicitud.whatsapp_step = str(STEP_HUMAN_HANDOFF)
                    solicitud.whatsapp_last_activity = datetime.utcnow()
                    solicitud.whatsapp_warning_sent = False
                    db.session.commit()

                _commit_session(telefono, session)
                return 'ok', 200

            if is_confirmation_negative(texto):
                mensaje_cierre = (
                    "Entendido. Este bot automático es solo para enturne. "
                    "Cuando necesites gestionar tu turno, escribe 'NUEVO' y Fisher te ayudará. ¡Hasta pronto!"
                )
                send_whatsapp_message(telefono, mensaje_cierre)
                reset_safety_reminder_counter(telefono)
                reset_contextual_memory(session)
                session['step'] = STEP_INACTIVE
                configurar_timeout_session(session, None)
                session['welcome_invalid_attempts'] = 0

                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.mensaje = 'Conversación cerrada: el usuario indicó que no era para enturne.'
                    solicitud.whatsapp_step = str(STEP_INACTIVE)
                    solicitud.whatsapp_timeout_minutes = 0
                    solicitud.whatsapp_warning_sent = False
                    solicitud.whatsapp_last_activity = datetime.utcnow()
                    solicitud.estado = 'preconfirmacion'
                    solicitud.asesor_pendiente = False
                    solicitud.asesor_pendiente_desde = None
                    db.session.commit()
                _commit_session(telefono, session)
                return 'ok', 200
            else:
                # Si responde cualquier cosa que no sea "no", asumir que quiere enturnar
                send_whatsapp_message(
                    telefono,
                    "🐶 Fisher 🐶: ¡Guau! Perfecto, amigo. Escribe la placa de tu camión para que pueda olfatear tus datos en la base de datos. ¡Estoy listo para ladrar tu información!"
                )
                session['step'] = 2
                configurar_timeout_session(session, 10)  # 10 minutos para ingresar placa
        elif step == 2:
            placa = texto.upper().replace(' ', '')
            conductor = buscar_conductor_por_placa(placa)
            if conductor:
                respuesta = (
                    f"🐶 Fisher 🐶: ¡Encontré tus datos! ¿Estos son correctos?\n"
                    f"Placa: {conductor['PLACA']}\n"
                    f"Placa remolque: {conductor['PLACA REMOLQUE']}\n"
                    f"Nombre: {conductor['NOMBRE CONDUCTOR']}\n"
                    f"N° Documento: {conductor['N° DOCUMENTO']}\n"
                    f"Celular: {conductor['CELULAR']}\n"
                    "Responde 'sí' si son correctos o 'no' si necesitas corregirlos. ¡Mi cola se mueve esperando tu confirmación!"
                )
                
                # Guardar directamente en la solicitud de la base de datos
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.nombre_completo = conductor['NOMBRE CONDUCTOR']
                    solicitud.placa = conductor['PLACA']
                    solicitud.placa_remolque = conductor['PLACA REMOLQUE']
                    solicitud.cedula = conductor['N° DOCUMENTO']
                    solicitud.celular = conductor['CELULAR']
                    solicitud.estado = 'preconfirmacion'
                    db.session.commit()
            else:
                respuesta = f"🐶 Fisher 🐶: ¡Guau! No se encontró conductor con placa {placa}. Por favor escribe tu nombre completo. ¡Estoy emocionado por conocerte!"
                # Guardar la placa original en la solicitud
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.placa = placa.upper()
                    db.session.commit()
                session['step'] = 10  # Nuevo paso para registro manual
            send_whatsapp_message(telefono, respuesta)
            session['step'] = 3
            configurar_timeout_session(session, 60)  # 60 minutos para confirmar datos
        elif step == 3:
            if is_confirmation_positive(texto):
                solicitud = session.get('solicitud')
                if solicitud and solicitud.estado != 'sin turno':
                    # El conductor confirmó sus datos; la solicitud ahora puede mostrarse en el panel
                    solicitud.estado = 'sin turno'
                    solicitud.fecha = datetime.utcnow()
                    db.session.commit()

                send_whatsapp_message(telefono, "🐶 Fisher 🐶: ¡Woof! Es hora de la guía. Envía la foto o PDF de tu guía de transporte. Mi nariz de perro detective revisará cada línea para que tu viaje sea impecable. ¡Vamos, no me dejes con la lengua afuera esperando!")
                session['step'] = 4
                configurar_timeout_session(session, None)  # Sin timeout después de confirmar datos
            else:
                # Usuario quiere corregir datos - iniciar registro manual
                send_whatsapp_message(telefono, "🐶 Fisher 🐶: Entendido, vamos a registrar tus datos manualmente.\n\nPor favor escribe tu nombre completo. ¡Estoy listo para aprender sobre ti!")
                session['step'] = 10
                configurar_timeout_session(session, 30)
        elif step == 4:
            if tipo == 'image' or tipo == 'document':
                media_payload = msg.get('image') or msg.get('document')
                guardar_imagen_whatsapp(telefono, media_payload, 'imagen_guia', session)
                # Después de guardar la guía, pedir el manifiesto (NO llamar a _prompt_for_next_pending_requirement)
                session['step'] = STEP_AWAIT_MANIFIESTO
                configurar_timeout_session(session, 60)  # 1 hora para manifiesto
                try:
                    send_whatsapp_message(telefono, "🐶 Fisher 🐶: ¡Guía recibida! Ahora necesito el manifiesto como imagen o PDF. Mi nariz está ansiosa por revisar todos los documentos. ¡Envíalo pronto para continuar con tu enturne!")
                except Exception:
                    current_app.logger.warning('No se pudo solicitar manifiesto a %s', telefono)
            else:
                hint = (
                    "Necesito la guía como imagen o PDF. No puedo procesar textos, notas de voz ni otros formatos en este paso."
                )
                fallback_msg = compose_contextual_hint(session, STEP_AWAIT_GUIA, hint)
                send_whatsapp_message(telefono, fallback_msg)
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 15:  # STEP_AWAIT_MANIFIESTO
            if tipo == 'image' or tipo == 'document':
                media_payload = msg.get('image') or msg.get('document')
                guardar_imagen_whatsapp(telefono, media_payload, 'imagen_manifiesto', session)
                solicitud = session.get('solicitud')
                _prompt_for_next_pending_requirement(session, solicitud, telefono)
            else:
                hint = (
                    "Necesito el manifiesto como imagen o PDF. No puedo procesar textos, notas de voz ni otros formatos en este paso."
                )
                fallback_msg = compose_contextual_hint(session, STEP_AWAIT_MANIFIESTO, hint)
                send_whatsapp_message(telefono, fallback_msg)
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 5:
            if tipo == 'location':
                loc = msg['location']
                
                # --- DETECCIÓN AVANZADA DE SPOOFING ---
                # 1. Verificar si es ubicación reenviada (forwarded)
                is_forwarded = msg.get('context') is not None
                
                # 2. Verificar si es lugar seleccionado del mapa
                has_name_or_address = loc.get('name') or loc.get('address')
                
                # 3. Si cualquiera de las dos condiciones se cumple, es spoofing
                if is_forwarded or has_name_or_address:
                    spoofing_message = _handle_spoofing_attempt(session, telefono, 'Bosconia')
                    send_whatsapp_message(telefono, spoofing_message, force_reminder=True)
                    _commit_session(telefono, session)
                    return 'ok', 200
                # -----------------------------------------
                
                lat = float(loc['latitude'])
                lng = float(loc['longitude'])
                
                if validar_y_guardar_ubicacion(telefono, lat, lng, 'bosconia', session, 6):
                    solicitud = session.get('solicitud')
                    _prompt_for_next_pending_requirement(session, solicitud, telefono)
            else:
                hint = (
                    "Comparte la ubicación en tiempo real desde Bosconia con el clip ➜ Ubicación. Solo puedo registrar ubicaciones, no mensajes ni imágenes, en este paso."
                )
                fallback_msg = compose_contextual_hint(session, STEP_AWAIT_GPS_BOSCONIA, hint)
                send_whatsapp_message(telefono, fallback_msg)
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 6:
            if tipo in ['image', 'document']:
                # --- DETECCIÓN DE TICKETS FORWARDED ---
                # Verificar si la imagen/documento es reenviado (forwarded)
                is_forwarded = msg.get('context') is not None
                
                if is_forwarded:
                    forwarded_message = _handle_forwarded_ticket_attempt(session, telefono, 'ticket de Gambote')
                    send_whatsapp_message(telefono, forwarded_message, force_reminder=True)
                    _commit_session(telefono, session)
                    return 'ok', 200
                # -----------------------------------------
                
                media_payload = msg.get('image') or msg.get('document')
                guardar_imagen_whatsapp(telefono, media_payload, 'ticket_gambote', session)
                solicitud = session.get('solicitud')
                _prompt_for_next_pending_requirement(session, solicitud, telefono)
            elif tipo == 'location':
                # Si envía ubicación en este paso, validar si es Gambote (quizás saltó el ticket)
                loc = msg['location']
                
                # --- DETECCIÓN AVANZADA DE SPOOFING ---
                # 1. Verificar si es ubicación reenviada (forwarded)
                is_forwarded = msg.get('context') is not None
                
                # 2. Verificar si es lugar seleccionado del mapa
                has_name_or_address = loc.get('name') or loc.get('address')
                
                # 3. Si cualquiera de las dos condiciones se cumple, es spoofing
                if is_forwarded or has_name_or_address:
                    spoofing_message = _handle_spoofing_attempt(session, telefono, 'Gambote')
                    send_whatsapp_message(telefono, spoofing_message, force_reminder=True)
                    _commit_session(telefono, session)
                    return 'ok', 200
                # -----------------------------------------
                
                lat = float(loc['latitude'])
                lng = float(loc['longitude'])
                
                if validar_y_guardar_ubicacion(telefono, lat, lng, 'gambote', session, 9):
                    solicitud = session.get('solicitud')
                    _prompt_for_next_pending_requirement(session, solicitud, telefono)
            else:
                hint = (
                    "Necesito la foto del ticket de Gambote como imagen o PDF. No puedo registrar textos, ubicaciones u otros adjuntos en este paso."
                )
                fallback_msg = compose_contextual_hint(session, STEP_AWAIT_TICKET_GAMBOTE, hint)
                send_whatsapp_message(telefono, fallback_msg)
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 7:
            if tipo == 'location':
                loc = msg['location']
                
                # --- DETECCIÓN AVANZADA DE SPOOFING ---
                # 1. Verificar si es ubicación reenviada (forwarded)
                is_forwarded = msg.get('context') is not None
                
                # 2. Verificar si es lugar seleccionado del mapa
                has_name_or_address = loc.get('name') or loc.get('address')
                
                # 3. Si cualquiera de las dos condiciones se cumple, es spoofing
                if is_forwarded or has_name_or_address:
                    spoofing_message = _handle_spoofing_attempt(session, telefono, 'Gambote')
                    send_whatsapp_message(telefono, spoofing_message, force_reminder=True)
                    _commit_session(telefono, session)
                    return 'ok', 200
                # -----------------------------------------
                
                lat = float(loc['latitude'])
                lng = float(loc['longitude'])

                if validar_y_guardar_ubicacion(telefono, lat, lng, 'gambote', session, 9):
                    solicitud = session.get('solicitud')
                    _prompt_for_next_pending_requirement(session, solicitud, telefono)
            else:
                hint = (
                    "Para validar Gambote necesito la ubicación en tiempo real con el clip ➜ Ubicación. Solo puedo recibir ubicaciones, no mensajes ni fotos, en este paso."
                )
                fallback_msg = compose_contextual_hint(session, STEP_AWAIT_GPS_GAMBOTE, hint)
                send_whatsapp_message(telefono, fallback_msg)
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 8:
            # Compatibilidad con sesiones antiguas que esperaban ZISA
            solicitud = session.get('solicitud')
            _prompt_for_next_pending_requirement(session, solicitud, telefono)
        elif step == 9:
            if is_confirmation_positive(texto):
                # La solicitud ya tiene todos los datos guardados, cambiar el estado a 'en revision' para aprobación humana
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.estado = 'en revision'
                    db.session.commit()
                
                send_whatsapp_message(telefono, "¡Perfecto! Fisher 🐶 ya envió tus datos a revisión. El personal de Conquers te notificará cuando estés aprobado y enturnado.")
                session['step'] = 'confirmed'  # Cambiar a estado confirmado
                configurar_timeout_session(session, None)  # Sin timeout después de confirmar
                session['post_confirm_messages'] = 0  # Inicializar contador de mensajes posteriores
                _commit_session(telefono, session)
                return 'ok', 200
            else:
                hint = "Confírmame con un 'sí' para enviar tus datos a revisión y continuar con tu enturnamiento."
                fallback_msg = compose_contextual_hint(session, STEP_FINAL_CONFIRMATION, hint)
                send_yes_no_prompt(telefono, fallback_msg, context_label='FINAL_CONFIRM')
                _commit_session(telefono, session)
                return 'ok', 200
        elif step == 'confirmed':
            # Manejar mensajes posteriores a la confirmación final
            solicitud = session.get('solicitud')
            if not solicitud:
                # Si no hay solicitud, reiniciar
                session['step'] = 0
                session['data'] = {}
                _commit_session(telefono, session)
                return 'ok', 200
            
            # Incrementar contador de mensajes
            msg_count = session.get('post_confirm_messages', 0) + 1
            session['post_confirm_messages'] = msg_count
            
            # Procesar mensaje con NLP si es texto
            if texto and 'asesor' not in texto.lower():
                doc = nlp(texto.lower())
                is_question = '?' in texto
                has_negative = any(token.lemma_ in ['no', 'mal', 'problema', 'esperar', 'urgente', 'rápido', 'pronto'] for token in doc)
                has_positive = any(token.lemma_ in ['gracias', 'bien', 'ok', 'entendido'] for token in doc)
                
                # Respuestas ingeniosas basadas en el tipo de mensaje y contador
                if msg_count >= 5:
                    # Amenaza con reinicio si es muy intenso
                    responses = [
                        "🐶 Fisher 🐶: ¡Guau! Mi cola está cansada de tanto ladrido. Si el equipo humano no responde pronto, tu proceso de enturne podría volver a empezar desde cero. ¡Paciencia, amigo!",
                        "🐕 Fisher 🐶: Estoy ladrando fuerte para llamar al equipo, pero si sigues insistiendo y no responden, podría tener que enterrar tu solicitud y empezar de nuevo. ¡Espera un poco más!",
                        "🐶 Fisher 🐶: Mi hocico está seco de tanto mensaje. Si el humano no llega pronto, tu enturne podría irse al parque de los olvidados. ¡Sé paciente, perrito!",
                    ]
                elif is_question:
                    responses = [
                        "🐶 Fisher 🐶: ¡Buena pregunta! El equipo humano está olfateando tu caso y te responderá pronto. Mientras, juega con tu pelota de paciencia.",
                        "🐕 Fisher 🐶: Estoy preguntando al equipo por ti. Pronto tendrás una respuesta jugosa. ¡No te rasques tanto!",
                        "🐶 Fisher 🐶: Mi nariz está trabajando para traerte la respuesta. El humano llegará ladrando noticias pronto. ¡Espera sentado!",
                    ]
                elif has_negative:
                    responses = [
                        "🐶 Fisher 🐶: Entiendo tu ladrido de impaciencia. El equipo está corriendo lo más rápido posible. ¡Pronto tendrás tu hueso de respuesta!",
                        "🐕 Fisher 🐶: ¡No te preocupes, amigo! Estoy moviendo la cola para acelerar al equipo. Tu respuesta viene en camino.",
                        "🐶 Fisher 🐶: Mi corazón de perro late por resolver esto rápido. El humano está en ello, ¡aguanta un poco más!",
                    ]
                elif has_positive:
                    responses = [
                        "🐶 Fisher 🐶: ¡Guau, gracias por la paciencia! El equipo humano está trabajando duro para darte la mejor respuesta.",
                        "🐕 Fisher 🐶: ¡Qué buen chico! Estoy ladrando al equipo para que te respondan pronto. ¡Sigue siendo paciente!",
                        "🐶 Fisher 🐶: ¡Excelente actitud! Mi cola se mueve de felicidad. Pronto el humano te traerá buenas noticias.",
                    ]
                else:
                    responses = [
                        "🐶 Fisher 🐶: ¡Estoy ladrando fuerte al equipo humano! Están trabajando para responderte lo más rápido posible. ¡Paciencia, mi amigo peludo!",
                        "🐕 Fisher 🐶: Mi hocico está ocupado transmitiendo tu mensaje. El equipo está olfateando la solución. ¡Pronto tendrás respuesta!",
                        "🐶 Fisher 🐶: ¡Guau! Estoy corriendo en círculos para llamar al humano. Tu caso está en buenas patas, ¡espera un poquito!",
                        "🐕 Fisher 🐶: Estoy moviendo la cola para acelerar el proceso. El equipo humano te responderá pronto. ¡Sé paciente como un buen perro!",
                    ]
                
                aviso = random.choice(responses)
                try:
                    send_whatsapp_message(telefono, aviso, skip_reminder=True)
                except Exception:
                    current_app.logger.warning('No se pudo enviar mensaje de espera inteligente a %s', telefono)
                else:
                    solicitud.whatsapp_last_activity = datetime.utcnow()
                    db.session.commit()
            else:
                # Si menciona 'asesor', escalar a humano
                if texto and 'asesor' in texto.lower():
                    send_whatsapp_message(
                        telefono,
                        "🐶 Fisher 🐶: ¡Entendido! Estoy ladrando fuerte para llamar a un asesor humano. Pronto te atenderán.",
                        skip_reminder=True
                    )
                    reset_contextual_memory(session)
                    session['step'] = STEP_HUMAN_HANDOFF
                    configurar_timeout_session(session, None)
                    if solicitud:
                        solicitud.asesor_pendiente = True
                        if not solicitud.asesor_pendiente_desde:
                            solicitud.asesor_pendiente_desde = datetime.utcnow()
                        solicitud.whatsapp_step = str(STEP_HUMAN_HANDOFF)
                        solicitud.whatsapp_last_activity = datetime.utcnow()
                        solicitud.whatsapp_warning_sent = False
                        db.session.commit()
            
            session['last_activity'] = datetime.now()
            _commit_session(telefono, session)
            return 'ok', 200
        elif step == 10:
            # Nuevo conductor - paso 1: nombre completo
            nombre_completo = texto.strip().title()
            if len(nombre_completo) < 3:
                send_whatsapp_message(telefono, "🐶 Fisher 🐶: El nombre debe tener al menos 3 caracteres. Por favor escribe tu nombre completo. ¡Mi olfato necesita más letras!")
                _commit_session(telefono, session)
                return 'ok', 200
            
            # Guardar directamente en la solicitud
            solicitud = session.get('solicitud')
            if solicitud:
                solicitud.nombre_completo = nombre_completo
                if not solicitud.celular:
                    solicitud.celular = telefono
                db.session.commit()
            
            send_whatsapp_message(telefono, f"🐶 Fisher 🐶: ¡Nombre registrado: {nombre_completo}! Mi memoria canina nunca olvida.\n\nAhora por favor escribe tu número de cédula. ¡Estoy olfateando tu identidad!")
            session['step'] = 11
            configurar_timeout_session(session, 30)
        elif step == 11:
            # Nuevo conductor - paso 2: cédula
            cedula = texto.strip().replace(' ', '').replace('.', '').replace('-', '')
            if not cedula.isdigit() or len(cedula) < 5:
                send_whatsapp_message(telefono, "🐶 Fisher 🐶: La cédula debe contener solo números y tener al menos 5 dígitos. Por favor escribe tu número de cédula. ¡Mi hocico está esperando números!")
                _commit_session(telefono, session)
                return 'ok', 200
            
            # Guardar directamente en la solicitud
            solicitud = session.get('solicitud')
            if solicitud:
                solicitud.cedula = cedula
                db.session.commit()
            
            send_whatsapp_message(telefono, f"🐶 Fisher 🐶: ¡Cédula registrada: {cedula}! Mi olfato está funcionando perfectamente.\n\nAhora por favor escribe la placa del remolque (o escribe 'NO' si no tienes remolque). ¡Estoy listo para más información!")
            session['step'] = 12
            configurar_timeout_session(session, 30)
        elif step == 12:
            # Nuevo conductor - paso 3: placa remolque
            if texto.upper() in ['NO', 'NINGUNO', 'SIN REMOLQUE', '-']:
                placa_remolque = ''
                # Guardar directamente en la solicitud
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.placa_remolque = ''
                    db.session.commit()
                mensaje_resumen = "Sin remolque registrado."
            else:
                placa_remolque = texto.upper().replace(' ', '')
                # Validar formato básico de placa
                if not placa_remolque or len(placa_remolque) < 3:
                    send_whatsapp_message(telefono, "🐶 Fisher 🐶: La placa del remolque debe tener al menos 3 caracteres. Por favor escribe la placa del remolque o 'NO' si no tienes. ¡Mi nariz está esperando!")
                    _commit_session(telefono, session)
                    return 'ok', 200
                
                # Guardar directamente en la solicitud
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.placa_remolque = placa_remolque
                    db.session.commit()
                
                mensaje_resumen = f"Placa remolque: {placa_remolque}"

            # Mostrar resumen completo de datos del nuevo conductor
            solicitud = session.get('solicitud')
            datos = get_solicitud_data(solicitud)
            
            resumen = (
                f"📋 *Resumen de tus datos:*\n\n"
                f"Nombre: {datos.get('nombre_completo')}\n"
                f"Cédula: {datos.get('cedula')}\n"
                f"Placa camión: {datos.get('placa')}\n"
                f"{mensaje_resumen}\n"
                f"Celular: {telefono}\n\n"
                f"¿Estos datos son correctos? Responde 'sí' para confirmar o 'no' para corregirlos."
            )
            send_yes_no_prompt(telefono, resumen, context_label='MANUAL_RES')
            session['step'] = 13
            manual_cfg = get_step_timeout_config(STEP_MANUAL_REG_CONFIRM)
            configurar_timeout_session(session, manual_cfg.get('timeout', 10))
        elif step == 13:
            # Nuevo conductor - paso 4: confirmación de datos
            if is_confirmation_positive(texto):
                solicitud = session.get('solicitud')
                if solicitud:
                    solicitud.estado = STATE_PENDING_INSCRIPTION
                    solicitud.fecha = datetime.utcnow()
                    solicitud.asesor_pendiente = True
                    solicitud.asesor_pendiente_desde = datetime.utcnow()
                    solicitud.whatsapp_step = STEP_HUMAN_HANDOFF
                    solicitud.whatsapp_timeout_minutes = 0
                    solicitud.whatsapp_warning_sent = False
                    solicitud.whatsapp_last_activity = datetime.utcnow()
                    if not solicitud.celular:
                        solicitud.celular = telefono
                    solicitud.mensaje = 'Registro manual pendiente de inscripción por asesor.'
                    marca = datetime.utcnow().strftime('%d/%m/%Y %H:%M')
                    nota = f"[{marca}] Datos confirmados por el conductor. Pendiente aprobación manual."
                    if solicitud.observaciones:
                        solicitud.observaciones = f"{solicitud.observaciones}\n{nota}"
                    else:
                        solicitud.observaciones = nota
                    db.session.commit()
                    if solicitud.id:
                        _cancel_final_timeout_message(solicitud.id)

                reset_contextual_memory(session)
                send_whatsapp_message(
                    telefono,
                    "🐶 Fisher 🐶: ¡Gracias! Guardé tus datos y los compartí con un asesor humano. Te escribirán pronto para completar tu inscripción. ¡Mi cola se mueve de felicidad!"
                )
                reset_safety_reminder_counter(telefono)
                session['step'] = STEP_HUMAN_HANDOFF
                configurar_timeout_session(session, 0)
                session['warning_sent'] = False
                session['last_activity'] = datetime.now()
            else:
                # Reiniciar proceso de registro manual
                send_whatsapp_message(telefono, "🐶 Fisher 🐶: Entendido, vamos a corregir tus datos.\n\nPor favor escribe tu nombre completo. ¡Estoy listo para empezar de nuevo!")
                session['step'] = 10
                configurar_timeout_session(session, 30)
        # Guardar el estado de la sesión en la base de datos
        _commit_session(telefono, session)
        return 'ok', 200
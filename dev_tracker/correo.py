"""
Envio de correo del modulo DevTracker.

Reutiliza la configuracion SMTP de Office 365 que ya usa el resto del sistema
(SMTP_SERVER / SMTP_PORT / SMTP_USER / SMTP_PASSWORD). Si falta la contraseña,
no se envia nada y no se rompe nada: se registra y sigue, igual que el resto
del repositorio.

Nada de esto corre durante una peticion web. Lo llama el trabajo del scheduler,
asi que una caida del servidor de correo jamas deja una pantalla colgada ni
impide guardar un ticket.
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

# Si no esta configurada, los correos salen sin botones (el texto igual sirve).
URL_BASE = os.getenv('APP_BASE_URL', '').rstrip('/')

COLOR_PRIMARIO = '#0d6efd'
COLOR_EXITO = '#198754'
COLOR_ALERTA = '#fd7e14'
COLOR_PELIGRO = '#dc3545'


def smtp_configurado():
    return bool(os.getenv('SMTP_PASSWORD'))


def enviar_smtp(destinatarios, asunto, html, texto):
    """Envia un correo. Devuelve True si salio, False si no. Nunca lanza."""
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]
    destinatarios = [d for d in destinatarios if d]
    if not destinatarios:
        return False

    servidor = os.getenv('SMTP_SERVER', 'smtp.office365.com')
    puerto = int(os.getenv('SMTP_PORT', 587))
    usuario = os.getenv('SMTP_USER', 'numbers@conquerstrading.com')
    clave = os.getenv('SMTP_PASSWORD')

    if not clave:
        log.warning('[DevTracker] SIMULACION correo -> %s | %s', destinatarios, asunto)
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f'DevTracker Conquers <{usuario}>'
        msg['To'] = ', '.join(destinatarios)
        msg['Subject'] = asunto
        msg.attach(MIMEText(texto, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        with smtplib.SMTP(servidor, puerto, timeout=30) as server:
            server.starttls()
            server.login(usuario, clave)
            server.sendmail(usuario, destinatarios, msg.as_string())
        log.info('[DevTracker] Correo enviado a %s: %s', destinatarios, asunto)
        return True
    except Exception as e:
        log.error('[DevTracker] Fallo al enviar correo a %s: %s', destinatarios, e)
        raise


def _boton(texto, ruta, color=COLOR_PRIMARIO):
    if not URL_BASE:
        return ''
    return (
        f'<table cellpadding="0" cellspacing="0" style="margin:24px 0"><tr><td '
        f'style="background:{color};border-radius:8px">'
        f'<a href="{URL_BASE}{ruta}" style="display:inline-block;padding:12px 24px;'
        f'color:#fff;text-decoration:none;font-weight:600;font-size:14px">{texto}</a>'
        f'</td></tr></table>'
    )


def envolver(titulo, franja, cuerpo_html, boton_html=''):
    """Plantilla comun. HTML de tablas, que es lo unico que Outlook respeta."""
    pie = (
        'Recibes este correo porque radicaste un requerimiento en el sistema '
        'de Conquers Trading.'
    )
    if URL_BASE:
        pie += f' Puedes desactivar los avisos desde <a href="{URL_BASE}/solicitudes" ' \
               f'style="color:#6c757d">tu portal</a>.'
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f4f5f7;
 font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:24px 12px">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0"
 style="max-width:560px;background:#fff;border-radius:14px;overflow:hidden;
 box-shadow:0 2px 8px rgba(0,0,0,.06)">
  <tr><td style="background:{franja};height:5px;font-size:0;line-height:0">&nbsp;</td></tr>
  <tr><td style="padding:28px 32px 8px">
    <h1 style="margin:0 0 4px;font-size:19px;color:#1a1d23;font-weight:700">{titulo}</h1>
  </td></tr>
  <tr><td style="padding:0 32px 28px;font-size:14px;line-height:1.6;color:#3c4149">
    {cuerpo_html}
    {boton_html}
  </td></tr>
  <tr><td style="padding:16px 32px;background:#fafbfc;border-top:1px solid #eceef1;
   font-size:11px;color:#8b939e;line-height:1.5">{pie}</td></tr>
</table>
<p style="margin:16px 0 0;font-size:11px;color:#a0a6ae">
 Conquers Trading &middot; Sistema de Gestión</p>
</td></tr></table>
</body></html>"""


def _dato(etiqueta, valor):
    if valor in (None, '', '—'):
        return ''
    return (
        f'<tr><td style="padding:5px 0;color:#8b939e;font-size:12px;width:150px;'
        f'vertical-align:top">{etiqueta}</td>'
        f'<td style="padding:5px 0;font-size:13px;color:#1a1d23;font-weight:600">{valor}</td></tr>'
    )


def tabla_datos(filas):
    contenido = ''.join(_dato(k, v) for k, v in filas)
    if not contenido:
        return ''
    return (
        '<table cellpadding="0" cellspacing="0" style="width:100%;margin:16px 0;'
        'background:#fafbfc;border-radius:10px;padding:8px 14px">'
        f'{contenido}</table>'
    )

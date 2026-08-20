"""
Tests del sistema de avisos por correo de DevTracker.

Lo que se verifica aqui no es que los correos salgan, sino que salgan POCOS:
que el silencio sea el estado por defecto, que un movimiento deshecho no le
llegue a nadie, y que varias fallas seguidas quepan en un solo correo.
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DEV_EMAIL = 'numbers@conquerstrading.com'
USUARIO_A = 'qualitycontrol@conquerstrading.com'


@pytest.fixture
def app():
    from flask import Flask
    from extensions import db as _db

    aplicacion = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'),
    )
    aplicacion.config['TESTING'] = True
    aplicacion.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    aplicacion.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    aplicacion.config['SECRET_KEY'] = 'test-secret'
    aplicacion.config['DEVTRACKER_ADMIN_EMAILS'] = [DEV_EMAIL]

    _db.init_app(aplicacion)

    import dev_tracker.models  # noqa: F401
    from dev_tracker.routes import dev_tracker_bp
    aplicacion.register_blueprint(dev_tracker_bp)

    with aplicacion.app_context():
        _db.create_all()
        from dev_tracker.models import sembrar_checklist_por_defecto
        sembrar_checklist_por_defecto()
        yield aplicacion
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def buzon(monkeypatch):
    """Captura los correos en vez de enviarlos por SMTP."""
    enviados = []

    def falso_enviar(destinatarios, asunto, html, texto):
        enviados.append({'para': destinatarios, 'asunto': asunto,
                         'html': html, 'texto': texto})
        return True

    import dev_tracker.notificaciones as noti
    monkeypatch.setattr(noti, 'enviar_smtp', falso_enviar)
    return enviados


def entrar(client, email, nombre='Usuario', rol='usuario', area=None):
    with client.session_transaction() as sesion:
        sesion['email'] = email
        sesion['nombre'] = nombre
        sesion['rol'] = rol
        sesion['area'] = area if area is not None else []


def radicar(client, titulo='Necesito un reporte'):
    return client.post('/api/solicitudes',
                       json={'titulo': titulo, 'descripcion': 'Detalle'})


def aceptar(client, ticket_id, prioridad='Alta', fecha_comprometida=None):
    return client.post(f'/api/dev-tracker/inbox/{ticket_id}/resolve', json={
        'accion': 'aceptar', 'prioridad': prioridad,
        'fecha_comprometida': fecha_comprometida,
    })


def vaciar_cola(app):
    """Vence la cola y la procesa, como haría el scheduler cada 2 minutos."""
    from extensions import db as _db
    from dev_tracker.models import CORREO_PENDIENTE, DevEmailOutbox
    import dev_tracker.notificaciones as noti

    with app.app_context():
        for fila in DevEmailOutbox.query.filter_by(estado=CORREO_PENDIENTE).all():
            fila.programado_para = datetime.utcnow() - timedelta(minutes=1)
        _db.session.commit()
    noti.procesar_cola(app)


def entregar(client, app, titulo='Reporte de tránsito'):
    """Deja un ticket de USUARIO_A en producción. Devuelve su id."""
    entrar(client, USUARIO_A, nombre='Juan Diego Cuadros')
    ticket_id = radicar(client, titulo).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id,
            fecha_comprometida=(date.today() + timedelta(days=5)).isoformat())
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Produccion', 'confirmar': True})
    vaciar_cola(app)
    return ticket_id


# ===========================================================================
# Silencio por defecto
# ===========================================================================

def test_radicar_no_manda_ningun_correo(client, app, buzon):
    """Acaba de verlo en pantalla: confirmarle por correo sería puro ruido."""
    entrar(client, USUARIO_A)
    radicar(client)
    vaciar_cola(app)
    assert buzon == []


def test_pasar_a_desarrollo_no_manda_correo(client, app, buzon):
    """'Ya empezamos' no cambia nada para quien pidió."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    vaciar_cola(app)
    buzon.clear()

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})
    vaciar_cola(app)
    assert buzon == []


def test_ticket_completo_genera_solo_dos_correos(client, app, buzon):
    """Camino feliz: aceptada y entregada. Nada más en todo el ciclo."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id,
            fecha_comprometida=(date.today() + timedelta(days=5)).isoformat())
    vaciar_cola(app)

    for nuevo in ('En Desarrollo', 'En Pruebas', 'En Produccion'):
        client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                   json={'estado': nuevo, 'confirmar': True})
        vaciar_cola(app)

    asuntos = [c['asunto'] for c in buzon]
    assert len(asuntos) == 2, f'esperaba 2 correos, llegaron {len(asuntos)}: {asuntos}'
    assert 'Aceptada' in asuntos[0]
    assert 'disponible' in asuntos[1]


# ===========================================================================
# Contenido util
# ===========================================================================

def test_aceptar_avisa_con_la_fecha_comprometida(client, app, buzon):
    """El dato que el solicitante no tiene: para cuándo se lo entregan."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    manana = (date.today() + timedelta(days=1)).isoformat()
    aceptar(client, ticket_id, prioridad='Alta', fecha_comprometida=manana)
    vaciar_cola(app)

    assert len(buzon) == 1
    assert buzon[0]['para'] == [USUARIO_A]
    assert manana in buzon[0]['asunto']
    assert 'Alta' in buzon[0]['html']


def test_devolver_incluye_el_comentario(client, app, buzon):
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    client.post(f'/api/dev-tracker/inbox/{ticket_id}/resolve',
                json={'accion': 'devolver', 'comentario': 'Falta decir de qué planta'})
    vaciar_cola(app)

    assert len(buzon) == 1
    assert 'Falta decir de qué planta' in buzon[0]['html']


def test_pruebas_solo_avisa_si_pido_validacion(client, app, buzon):
    """Avisar sin pedirle nada es ruido; pedirle que valide sí es acción."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    vaciar_cola(app)
    buzon.clear()

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Pruebas', 'confirmar': True})
    vaciar_cola(app)
    assert buzon == []

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Pruebas', 'confirmar': True,
                     'solicitar_validacion': True})
    vaciar_cola(app)
    assert len(buzon) == 1
    assert 'pruebes' in buzon[0]['asunto']


# ===========================================================================
# La red de seguridad
# ===========================================================================

def test_el_aviso_se_cancela_si_deshago_el_movimiento(client, app, buzon):
    """
    Arrastro a Producción por error y lo devuelvo antes de los 10 minutos.
    El solicitante nunca se entera.
    """
    from dev_tracker.models import CORREO_CANCELADO, DevEmailOutbox

    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    vaciar_cola(app)
    buzon.clear()

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Produccion', 'confirmar': True})
    assert buzon == [], 'no debe salir nada de inmediato'

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})

    vaciar_cola(app)
    assert buzon == [], 'el aviso debió cancelarse solo'

    with app.app_context():
        fila = DevEmailOutbox.query.filter_by(evento='estado_produccion').first()
        assert fila.estado == CORREO_CANCELADO


def test_no_se_encola_dos_veces_el_mismo_aviso(client, app, buzon):
    """Doble clic o reintento: una sola fila, un solo correo."""
    from dev_tracker.models import DevEmailOutbox

    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    aceptar(client, ticket_id)  # segundo intento

    with app.app_context():
        assert DevEmailOutbox.query.filter_by(evento='triage_aceptada').count() == 1

    vaciar_cola(app)
    assert len(buzon) == 1


# ===========================================================================
# Fallas y resumen
# ===========================================================================

def test_fallas_en_produccion_llegan_agrupadas(client, app, buzon):
    """Tres fallas seguidas = un correo, no tres."""
    ticket_id = entregar(client, app)
    buzon.clear()

    entrar(client, USUARIO_A)
    for texto in ('El PDF sale vacío', 'No filtra por fecha', 'Se cae al exportar'):
        client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                    json={'descripcion': texto})

    vaciar_cola(app)
    assert len(buzon) == 1, 'las fallas deben agruparse en un solo correo'
    assert 'El PDF sale vacío' in buzon[0]['html']
    assert 'Se cae al exportar' in buzon[0]['html']
    assert buzon[0]['para'] == [DEV_EMAIL]


def test_falla_en_pruebas_no_interrumpe(client, app, buzon):
    """Solo lo que está en producción justifica romper el resumen diario."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']
    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Pruebas', 'confirmar': True})
    vaciar_cola(app)
    buzon.clear()

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                json={'descripcion': 'Detalle menor en pruebas'})
    vaciar_cola(app)
    assert buzon == []


def test_resumen_diario_no_sale_si_no_hay_nada(app, buzon):
    """Un correo que dice 'sin novedades' enseña a ignorar al remitente."""
    from dev_tracker.notificaciones import enviar_resumen_diario
    enviar_resumen_diario(app)
    assert buzon == []


def test_resumen_diario_junta_todo_en_un_correo(client, app, buzon):
    from dev_tracker.notificaciones import enviar_resumen_diario

    entrar(client, USUARIO_A)
    radicar(client, titulo='Solicitud sin triar')

    entrar(client, DEV_EMAIL)
    client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Ya venció', 'prioridad': 'Alta',
        'fecha_comprometida': (date.today() - timedelta(days=4)).isoformat()})
    buzon.clear()

    enviar_resumen_diario(app)

    assert len(buzon) == 1, 'todo debe caber en un solo resumen'
    assert buzon[0]['para'] == [DEV_EMAIL]
    assert 'Solicitud sin triar' in buzon[0]['html']
    assert 'Ya venció' in buzon[0]['html']
    assert '1 por revisar' in buzon[0]['asunto']


# ===========================================================================
# Preferencias y seguridad
# ===========================================================================

def test_apagar_avisos_deja_de_encolar(client, app, buzon):
    from dev_tracker.models import DevEmailOutbox

    entrar(client, USUARIO_A)
    assert client.post('/api/solicitudes/preferencias-correo',
                       json={'activo': False}).status_code == 200
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)

    with app.app_context():
        assert DevEmailOutbox.query.count() == 0
    vaciar_cola(app)
    assert buzon == []


def test_el_titulo_no_puede_inyectar_html(client, app, buzon):
    """El título lo escribe el solicitante: va escapado en el correo."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(
        client, '<script>alert(1)</script> Reporte'
    ).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    vaciar_cola(app)

    assert '<script>' not in buzon[0]['html']
    assert '&lt;script&gt;' in buzon[0]['html']

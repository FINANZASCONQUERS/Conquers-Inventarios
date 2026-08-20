"""
Tests del modulo DevTracker.

Cubren los riesgos que importan, en este orden:
1. Seguridad: que el solicitante no pueda inyectar prioridad ni fecha, que no
   vea lo ajeno, y que el tablero no se abra a quien tiene rol admin pero no es
   el desarrollador.
2. Reglas de negocio con dinero de por medio: preservacion de la fecha
   comprometida original y exclusion de lo no aceptado en las metricas.
3. Zona horaria: que un ticket que vence hoy no salga retrasado a las 8 p.m.
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest
import pytz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

DEV_EMAIL = 'numbers@conquerstrading.com'
USUARIO_A = 'qualitycontrol@conquerstrading.com'
USUARIO_B = 'logistic@conquerstrading.com'


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


def entrar(client, email, nombre='Usuario', rol='usuario', area=None):
    """Simula la sesion que arma el login de app.py."""
    with client.session_transaction() as sesion:
        sesion['email'] = email
        sesion['nombre'] = nombre
        sesion['rol'] = rol
        sesion['area'] = area if area is not None else []


def radicar(client, titulo='Necesito un reporte', **extra):
    cuerpo = {'titulo': titulo, 'descripcion': 'Detalle del requerimiento'}
    cuerpo.update(extra)
    return client.post('/api/solicitudes', json=cuerpo)


def aceptar(client, ticket_id, prioridad='Alta', fecha_comprometida=None):
    return client.post(
        f'/api/dev-tracker/inbox/{ticket_id}/resolve',
        json={
            'accion': 'aceptar',
            'prioridad': prioridad,
            'fecha_comprometida': fecha_comprometida,
        },
    )


# ===========================================================================
# 1. Seguridad
# ===========================================================================

def test_radicar_ignora_prioridad_y_fecha_inyectadas(client, app):
    """FR-041: el solicitante propone, no compromete. Se impone en el servidor."""
    entrar(client, USUARIO_A, nombre='Juan Diego Cuadros', area=['barcaza_orion'])

    respuesta = radicar(
        client,
        titulo='Quiero esto ya',
        prioridad='Alta',
        fecha_comprometida='2026-08-08',
        estado='En Produccion',
        origen='directo',
        solicitante_nombre='Otro Nombre',
    )
    assert respuesta.status_code == 201

    with app.app_context():
        from dev_tracker.models import DevTicket, ESTADO_POR_REVISAR
        ticket = DevTicket.query.first()
        assert ticket.prioridad is None, 'el solicitante no puede fijar prioridad'
        assert ticket.fecha_comprometida is None, 'el solicitante no puede comprometer fecha'
        assert ticket.estado == ESTADO_POR_REVISAR, 'toda solicitud entra a la bandeja'
        assert ticket.origen == 'portal'
        # La firma sale de la sesion, no del payload.
        assert ticket.solicitante_nombre == 'Juan Diego Cuadros'
        assert ticket.solicitante_email == USUARIO_A


def test_solicitante_no_ve_tickets_de_otro(client):
    """FR-051: aislamiento verificado por endpoint, no solo con el filtro de /mias."""
    entrar(client, USUARIO_A)
    ticket_de_a = radicar(client, titulo='Lo de A').get_json()['solicitud']['id']

    entrar(client, USUARIO_B)
    radicar(client, titulo='Lo de B')

    # B no puede leer el de A por id directo.
    assert client.get(f'/api/solicitudes/{ticket_de_a}').status_code == 403

    # Y su listado solo trae lo suyo.
    mias = client.get('/api/solicitudes/mias').get_json()['solicitudes']
    assert len(mias) == 1
    assert mias[0]['titulo'] == 'Lo de B'


def test_rol_admin_no_basta_para_entrar_al_tablero(client):
    """
    En este sistema rol='admin' lo tienen 3 personas y significa "ve todo el
    inventario". El tablero es del desarrollador: lista blanca por correo.
    """
    entrar(client, 'oci@conquerstrading.com', nombre='Carlos Barón', rol='admin')

    assert client.get('/dev-tracker').status_code == 403
    assert client.get('/api/dev-tracker/tickets').status_code == 403
    assert client.get('/api/dev-tracker/inbox').status_code == 403
    assert client.get('/api/dev-tracker/metrics').status_code == 403
    assert client.get('/api/dev-tracker/export').status_code == 403


def test_sin_sesion_no_entra_a_ningun_lado(client):
    assert client.get('/api/solicitudes/mias').status_code == 401
    assert client.get('/api/dev-tracker/tickets').status_code == 401


def test_re_radicar_solo_si_es_propia_y_esta_devuelta(client):
    """
    Las dos condiciones son necesarias. Sin la del estado, cualquiera podria
    reescribir un ticket ya en desarrollo y cambiarle el alcance por debajo.
    """
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    # Otro usuario no puede tocarla.
    entrar(client, USUARIO_B)
    assert client.put(f'/api/solicitudes/{ticket_id}/re-radicar',
                      json={'titulo': 'secuestrada'}).status_code == 403

    # El dueño tampoco, mientras no este devuelta.
    entrar(client, USUARIO_A)
    assert client.put(f'/api/solicitudes/{ticket_id}/re-radicar',
                      json={'titulo': 'otra cosa'}).status_code == 409

    # Se devuelve, y ahora si.
    entrar(client, DEV_EMAIL)
    client.post(f'/api/dev-tracker/inbox/{ticket_id}/resolve',
                json={'accion': 'devolver', 'comentario': 'Falta el detalle'})

    entrar(client, USUARIO_A)
    respuesta = client.put(f'/api/solicitudes/{ticket_id}/re-radicar',
                           json={'titulo': 'Ahora sí con detalle'})
    assert respuesta.status_code == 200
    assert respuesta.get_json()['solicitud']['estado'] == 'Por revisar'


def test_re_radicar_de_ticket_en_desarrollo_falla(client):
    """El caso concreto: ya esta en el tablero, nadie lo reescribe desde el portal."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})

    entrar(client, USUARIO_A)
    assert client.put(f'/api/solicitudes/{ticket_id}/re-radicar',
                      json={'titulo': 'cambiado'}).status_code == 409


def test_portal_no_expone_bugs_ni_checklist(client):
    """FR-052: el solicitante ve etapa y fechas, nada del detalle interno."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id)
    client.post(f'/api/dev-tracker/tickets/{ticket_id}/bugs',
                json={'descripcion': 'Falla interna', 'severidad': 'Critico'})

    entrar(client, USUARIO_A)
    datos = client.get(f'/api/solicitudes/{ticket_id}').get_json()['solicitud']
    for campo in ('bugs', 'checklist', 'notas_dev', 'transiciones', 'dias_retraso'):
        assert campo not in datos, f'{campo} no debe llegar al portal del solicitante'


# ===========================================================================
# 2. Triage y flujo
# ===========================================================================

def test_aceptar_exige_prioridad_y_mueve_al_tablero(client):
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    # Sin prioridad no se acepta.
    sin_prioridad = client.post(f'/api/dev-tracker/inbox/{ticket_id}/resolve',
                                json={'accion': 'aceptar'})
    assert sin_prioridad.status_code == 400

    manana = (date.today() + timedelta(days=1)).isoformat()
    respuesta = aceptar(client, ticket_id, prioridad='Alta', fecha_comprometida=manana)
    assert respuesta.status_code == 200

    ticket = respuesta.get_json()['ticket']
    assert ticket['estado'] == 'Solicitado'
    assert ticket['prioridad'] == 'Alta'
    assert ticket['fecha_comprometida'] == manana
    # FR-022: al entrar al flujo trae la lista de revision de la plantilla.
    assert ticket['checklist_total'] > 0


def test_solicitud_en_bandeja_no_aparece_en_el_tablero(client):
    """FR-042: nada entra al tablero sin ser aceptado."""
    entrar(client, USUARIO_A)
    radicar(client, titulo='Aún sin triar')

    entrar(client, DEV_EMAIL)
    tablero = client.get('/api/dev-tracker/tickets').get_json()
    assert tablero['total'] == 0

    bandeja = client.get('/api/dev-tracker/inbox').get_json()
    assert bandeja['total_pendientes'] == 1


def test_flujo_completo_registra_fechas_reales(client, app):
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Registro directo por WhatsApp',
        'prioridad': 'Media',
        'fecha_comprometida': (date.today() + timedelta(days=10)).isoformat(),
    }).get_json()['ticket']['id']

    for nuevo in ('En Desarrollo', 'En Pruebas', 'En Produccion'):
        respuesta = client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                               json={'estado': nuevo, 'confirmar': True})
        assert respuesta.status_code == 200

    with app.app_context():
        from dev_tracker.models import DevTicket
        ticket = DevTicket.query.get(ticket_id)
        assert ticket.fecha_inicio_desarrollo is not None
        assert ticket.fecha_entrada_pruebas is not None
        assert ticket.fecha_salida_produccion is not None
        # FR-010: cuatro transiciones (creacion + tres movimientos).
        assert len(ticket.transiciones) == 4


def test_retroceso_no_borra_fechas_del_ciclo_anterior(client, app):
    """Caso borde: vuelve de produccion a desarrollo y se conserva la historia."""
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Se rompio en produccion', 'prioridad': 'Alta',
    }).get_json()['ticket']['id']

    for nuevo in ('En Desarrollo', 'En Pruebas', 'En Produccion'):
        client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                   json={'estado': nuevo, 'confirmar': True})

    with app.app_context():
        from dev_tracker.models import DevTicket
        salida_original = DevTicket.query.get(ticket_id).fecha_salida_produccion

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})

    with app.app_context():
        from dev_tracker.models import DevTicket
        ticket = DevTicket.query.get(ticket_id)
        assert ticket.estado == 'En Desarrollo'
        assert ticket.fecha_salida_produccion == salida_original
        assert ticket.transiciones[-1].estado_origen == 'En Produccion'


def test_reactivar_rechazada_vuelve_a_la_bandeja(client):
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    client.post(f'/api/dev-tracker/inbox/{ticket_id}/resolve',
                json={'accion': 'rechazar', 'comentario': 'No procede por ahora'})

    respuesta = client.post(f'/api/dev-tracker/tickets/{ticket_id}/reactivar')
    assert respuesta.status_code == 200
    assert respuesta.get_json()['ticket']['estado'] == 'Por revisar'


# ===========================================================================
# 3. Advertencias antes de produccion
# ===========================================================================

def test_bug_critico_abierto_exige_confirmacion(client):
    """FR-021: advierte y exige confirmacion, no prohibe."""
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Con bug critico', 'prioridad': 'Alta',
    }).get_json()['ticket']['id']

    client.post(f'/api/dev-tracker/tickets/{ticket_id}/bugs',
                json={'descripcion': 'Rompe el cierre de mes', 'severidad': 'Critico'})

    bloqueado = client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                           json={'estado': 'En Produccion'})
    assert bloqueado.status_code == 409
    datos = bloqueado.get_json()
    assert datos['requiere_confirmacion'] is True
    assert any('crítico' in a.lower() for a in datos['advertencias'])

    # Con confirmacion explicita si pasa.
    confirmado = client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                            json={'estado': 'En Produccion', 'confirmar': True})
    assert confirmado.status_code == 200


def test_checklist_pendiente_exige_confirmacion(client):
    """FR-025."""
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Sin revisar nada', 'prioridad': 'Media',
    }).get_json()['ticket']['id']

    respuesta = client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                           json={'estado': 'En Produccion'})
    assert respuesta.status_code == 409
    assert any('revisión' in a.lower() for a in respuesta.get_json()['advertencias'])


def test_fechas_incoherentes_advierten(client):
    """FR-011: produccion antes que pruebas."""
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Fechas al reves', 'prioridad': 'Baja',
    }).get_json()['ticket']['id']

    respuesta = client.put(f'/api/dev-tracker/tickets/{ticket_id}', json={
        'fecha_entrada_pruebas': '2026-08-10',
        'fecha_salida_produccion': '2026-08-05',
    })
    assert respuesta.status_code == 409
    assert any('anterior a la entrada a pruebas' in a
               for a in respuesta.get_json()['advertencias'])


def test_bug_corregido_no_cuenta_pero_no_desaparece(client):
    """FR-019."""
    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Dos errores', 'prioridad': 'Media',
    }).get_json()['ticket']['id']

    bug_id = client.post(f'/api/dev-tracker/tickets/{ticket_id}/bugs',
                         json={'descripcion': 'Uno', 'severidad': 'Mayor'}
                         ).get_json()['bug']['id']
    client.post(f'/api/dev-tracker/tickets/{ticket_id}/bugs',
                json={'descripcion': 'Dos', 'severidad': 'Menor'})

    respuesta = client.put(f'/api/dev-tracker/bugs/{bug_id}', json={'estado': 'Corregido'})
    ticket = respuesta.get_json()['ticket']

    assert ticket['bugs_abiertos'] == 1
    assert ticket['severidad_maxima'] == 'Menor'
    assert len(ticket['bugs']) == 2, 'el corregido sigue en el historial'


# ===========================================================================
# 4. Fechas, plazos y zona horaria
# ===========================================================================

def test_fecha_comprometida_original_no_se_mueve(client, app):
    """
    FR-004. Si la original se pudiera correr junto con la nueva, mover la fecha
    borraria el incumplimiento y el porcentaje de cumplimiento no serviria.
    """
    entrar(client, DEV_EMAIL)
    original = (date.today() + timedelta(days=3)).isoformat()
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Me dieron mas plazo', 'prioridad': 'Alta',
        'fecha_comprometida': original,
    }).get_json()['ticket']['id']

    nueva = (date.today() + timedelta(days=15)).isoformat()
    respuesta = client.put(f'/api/dev-tracker/tickets/{ticket_id}',
                           json={'fecha_comprometida': nueva, 'confirmar': True})
    ticket = respuesta.get_json()['ticket']

    assert ticket['fecha_comprometida'] == nueva
    assert ticket['fecha_comprometida_original'] == original
    assert ticket['fecha_comprometida_movida'] is True


def test_estados_de_plazo(client):
    """FR-012, FR-013: retrasado, por vencer y a tiempo."""
    entrar(client, DEV_EMAIL)
    casos = {
        'Vencido': (date.today() - timedelta(days=3), 'retrasado'),
        'Manana': (date.today() + timedelta(days=1), 'por_vencer'),
        'Lejano': (date.today() + timedelta(days=20), 'a_tiempo'),
    }
    ids = {}
    for titulo, (fecha, _) in casos.items():
        ids[titulo] = client.post('/api/dev-tracker/tickets', json={
            'titulo': titulo, 'prioridad': 'Media',
            'fecha_comprometida': fecha.isoformat(),
        }).get_json()['ticket']['id']

    tickets = client.get('/api/dev-tracker/tickets').get_json()['tickets']
    por_titulo = {t['titulo']: t for t in tickets}
    for titulo, (_, esperado) in casos.items():
        assert por_titulo[titulo]['estado_plazo'] == esperado, titulo


def test_ticket_sin_fecha_no_genera_alertas(client):
    """FR-003: sin compromiso de fecha no hay retraso posible."""
    entrar(client, DEV_EMAIL)
    client.post('/api/dev-tracker/tickets',
                json={'titulo': 'Sin compromiso', 'prioridad': 'Baja'})

    ticket = client.get('/api/dev-tracker/tickets').get_json()['tickets'][0]
    assert ticket['estado_plazo'] == 'sin_fecha'
    assert ticket['dias_retraso'] is None


def test_dias_se_calculan_en_bogota_no_en_utc(app):
    """
    El bug que esto evita: a las 8 p.m. hora Colombia el servidor UTC ya esta en
    el dia siguiente. Un ticket que vence hoy apareceria retrasado esa tarde.
    """
    from dev_tracker.tiempo import BOGOTA_TZ, fecha_bogota, hoy_bogota

    # 7 de agosto de 2026, 8:30 p.m. en Bogota = 8 de agosto 01:30 UTC.
    noche_bogota = BOGOTA_TZ.localize(datetime(2026, 8, 7, 20, 30))
    equivalente_utc = noche_bogota.astimezone(pytz.utc).replace(tzinfo=None)

    assert equivalente_utc.date() == date(2026, 8, 8), 'en UTC ya es el dia siguiente'
    assert fecha_bogota(equivalente_utc) == date(2026, 8, 7), 'en Bogota sigue siendo hoy'

    # Y hoy_bogota nunca se adelanta respecto de la fecha UTC.
    assert hoy_bogota() in (datetime.utcnow().date(),
                            datetime.utcnow().date() - timedelta(days=1))


def test_entrega_a_tiempo_y_fuera_de_plazo(client, app):
    """FR-016."""
    from extensions import db as _db

    entrar(client, DEV_EMAIL)
    ticket_id = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Entregado tarde', 'prioridad': 'Alta',
        'fecha_comprometida': (date.today() - timedelta(days=5)).isoformat(),
    }).get_json()['ticket']['id']

    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Produccion', 'confirmar': True})

    with app.app_context():
        from dev_tracker.models import DevTicket
        ticket = _db.session.get(DevTicket, ticket_id)
        assert ticket.estado_plazo == 'entregado_tarde'
        assert ticket.dias_diferencia == -5


# ===========================================================================
# 5. Metricas, filtros y exportacion
# ===========================================================================

def test_metricas_excluyen_lo_no_aceptado(client):
    """
    FR-050. Contar una solicitud rechazada como incumplimiento seria falso: el
    desarrollador nunca se comprometio con ella.
    """
    entrar(client, USUARIO_A)
    rechazable = radicar(client, titulo='No procede').get_json()['solicitud']['id']
    radicar(client, titulo='Aún en bandeja')

    entrar(client, DEV_EMAIL)
    client.post(f'/api/dev-tracker/inbox/{rechazable}/resolve',
                json={'accion': 'rechazar', 'comentario': 'Ya existe'})

    entregado = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Entregado a tiempo', 'prioridad': 'Alta',
        'fecha_comprometida': (date.today() + timedelta(days=5)).isoformat(),
    }).get_json()['ticket']['id']
    client.put(f'/api/dev-tracker/tickets/{entregado}',
               json={'estado': 'En Produccion', 'confirmar': True})

    m = client.get('/api/dev-tracker/metrics').get_json()['metricas']
    assert m['total_activos'] == 0
    assert m['entregados_total'] == 1
    assert m['pct_cumplimiento'] == 100.0
    assert m['bandeja_pendiente'] == 1


def test_filtros_y_busqueda(client):
    """FR-029, FR-030."""
    entrar(client, DEV_EMAIL)
    client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Reporte de tránsito', 'prioridad': 'Alta',
        'solicitante_nombre': 'Contabilidad',
    })
    client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Ajuste de inventario', 'prioridad': 'Baja',
        'solicitante_nombre': 'Logística',
    })

    assert client.get('/api/dev-tracker/tickets?q=tránsito').get_json()['total'] == 1
    assert client.get('/api/dev-tracker/tickets?prioridad=Baja').get_json()['total'] == 1
    assert client.get(
        '/api/dev-tracker/tickets?solicitante=Contabilidad').get_json()['total'] == 1
    assert client.get('/api/dev-tracker/tickets?origen=directo').get_json()['total'] == 2
    assert client.get('/api/dev-tracker/tickets?origen=portal').get_json()['total'] == 0


def test_columna_produccion_muestra_lo_reciente_y_oculta_lo_viejo(client, app):
    """
    Mi correccion al plan: si la vista activa excluyera todo lo que esta en
    produccion, la cuarta columna del Kanban saldria siempre vacia.
    """
    from extensions import db as _db

    entrar(client, DEV_EMAIL)
    reciente = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Entregado ayer', 'prioridad': 'Media',
    }).get_json()['ticket']['id']
    viejo = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Entregado hace meses', 'prioridad': 'Media',
    }).get_json()['ticket']['id']

    for tid in (reciente, viejo):
        client.put(f'/api/dev-tracker/tickets/{tid}',
                   json={'estado': 'En Produccion', 'confirmar': True})

    with app.app_context():
        from dev_tracker.models import DevTicket
        antiguo = _db.session.get(DevTicket, viejo)
        antiguo.fecha_salida_produccion = datetime.utcnow() - timedelta(days=120)
        _db.session.commit()

    titulos = [t['titulo'] for t in
               client.get('/api/dev-tracker/tickets').get_json()['tickets']]
    assert 'Entregado ayer' in titulos, 'la columna En Producción no puede quedar vacía'
    assert 'Entregado hace meses' not in titulos

    # FR-033: lo viejo sigue consultable por el histórico.
    historico = [t['titulo'] for t in
                 client.get('/api/dev-tracker/tickets?historico=true').get_json()['tickets']]
    assert 'Entregado hace meses' in historico


def test_checklist_personalizado_no_toca_la_plantilla(client):
    """FR-023, FR-026."""
    entrar(client, DEV_EMAIL)
    uno = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Primero', 'prioridad': 'Media'}).get_json()['ticket']
    total_plantilla = uno['checklist_total']

    client.post(f'/api/dev-tracker/tickets/{uno["id"]}/checklist/items',
                json={'texto': 'Revisar el cron de las 6 a.m.'})

    dos = client.post('/api/dev-tracker/tickets', json={
        'titulo': 'Segundo', 'prioridad': 'Media'}).get_json()['ticket']
    assert dos['checklist_total'] == total_plantilla, \
        'el punto propio de un ticket no debe filtrarse a los demás'


def test_exportacion_csv_y_json(client):
    """FR-034."""
    entrar(client, DEV_EMAIL)
    client.post('/api/dev-tracker/tickets',
                json={'titulo': 'Para exportar', 'prioridad': 'Alta'})

    csv_resp = client.get('/api/dev-tracker/export?formato=csv')
    assert csv_resp.status_code == 200
    assert 'text/csv' in csv_resp.headers['Content-Type']
    assert 'attachment' in csv_resp.headers['Content-Disposition']
    assert b'Para exportar' in csv_resp.data

    json_resp = client.get('/api/dev-tracker/export?formato=json')
    assert json_resp.status_code == 200
    assert json_resp.get_json()['total'] == 1


# ===========================================================================
# 6. Despues de entregado: reportar falla vs. pedir ajuste
# ===========================================================================

def entregar(client, titulo='Reporte de tránsito'):
    """Deja un ticket radicado por USUARIO_A en produccion. Devuelve su id."""
    entrar(client, USUARIO_A, nombre='Juan Diego Cuadros')
    ticket_id = radicar(client, titulo=titulo).get_json()['solicitud']['id']

    entrar(client, DEV_EMAIL)
    aceptar(client, ticket_id, fecha_comprometida=(date.today() + timedelta(days=5)).isoformat())
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Produccion', 'confirmar': True})
    return ticket_id


def test_reportar_falla_entra_sin_clasificar(client, app):
    """
    El solicitante reporta, el desarrollador clasifica. Si el solicitante
    pudiera marcar 'Critico' controlaria el freno de despliegue desde afuera.
    """
    ticket_id = entregar(client)

    entrar(client, USUARIO_A)
    respuesta = client.post(f'/api/solicitudes/{ticket_id}/reportar-falla', json={
        'descripcion': 'Le doy clic al botón y sale error 500',
        'severidad': 'Critico',  # intento de inyeccion: debe ignorarse
    })
    assert respuesta.status_code == 201

    with app.app_context():
        from dev_tracker.models import DevTicketBug, SEVERIDAD_SIN_CLASIFICAR
        bug = DevTicketBug.query.first()
        assert bug.severidad == SEVERIDAD_SIN_CLASIFICAR
        assert bug.reportado_por == USUARIO_A
        assert bug.etapa_deteccion == 'Produccion'


def test_falla_reportada_no_cambia_el_estado_ni_la_fecha_de_entrega(client, app):
    """
    Lo importante para la métrica: una falla encontrada después no puede
    convertir retroactivamente en tardía una entrega que sí fue a tiempo.
    """
    ticket_id = entregar(client)

    with app.app_context():
        from dev_tracker.models import DevTicket
        from extensions import db as _db
        antes = _db.session.get(DevTicket, ticket_id)
        entrega_original = antes.fecha_salida_produccion
        plazo_antes = antes.estado_plazo

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                json={'descripcion': 'No me cuadra el total'})

    with app.app_context():
        from dev_tracker.models import DevTicket
        from extensions import db as _db
        despues = _db.session.get(DevTicket, ticket_id)
        assert despues.estado == 'En Produccion', 'reportar no mueve el ticket solo'
        assert despues.fecha_salida_produccion == entrega_original
        assert despues.estado_plazo == plazo_antes == 'entregado_a_tiempo'


def test_falla_sin_clasificar_aparece_en_la_bandeja(client):
    ticket_id = entregar(client)

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                json={'descripcion': 'Se cae al exportar'})

    entrar(client, DEV_EMAIL)
    bandeja = client.get('/api/dev-tracker/inbox').get_json()
    assert bandeja['total_fallas'] == 1
    assert bandeja['total_por_atender'] == 1
    falla = bandeja['fallas_por_clasificar'][0]
    assert falla['ticket_code'].startswith('DEV-')
    assert falla['reportado_por'] == USUARIO_A


def test_desarrollador_clasifica_y_ahi_si_frena_el_despliegue(client):
    """Una falla sin clasificar no dispara el freno; clasificada como crítica sí."""
    ticket_id = entregar(client)

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                json={'descripcion': 'Error al guardar'})

    entrar(client, DEV_EMAIL)
    bug_id = client.get('/api/dev-tracker/inbox').get_json()['fallas_por_clasificar'][0]['id']

    # Devolver a desarrollo y volver a producción: advierte por no clasificada.
    client.put(f'/api/dev-tracker/tickets/{ticket_id}',
               json={'estado': 'En Desarrollo', 'confirmar': True})
    aviso = client.put(f'/api/dev-tracker/tickets/{ticket_id}', json={'estado': 'En Produccion'})
    assert aviso.status_code == 409
    assert any('no ha clasificado' in a for a in aviso.get_json()['advertencias'])

    # Clasificada como crítica, ahora el aviso es el de FR-021.
    client.put(f'/api/dev-tracker/bugs/{bug_id}', json={'severidad': 'Critico'})
    aviso2 = client.put(f'/api/dev-tracker/tickets/{ticket_id}', json={'estado': 'En Produccion'})
    assert aviso2.status_code == 409
    assert any('crítico' in a.lower() for a in aviso2.get_json()['advertencias'])


def test_solicitar_ajuste_crea_ticket_nuevo_vinculado(client, app):
    """
    Caso B. Si reabriera el original, el tablero diría que ese desarrollo tomó
    semanas cuando en realidad se entregó a tiempo.
    """
    original_id = entregar(client, titulo='Reporte de tránsito')

    entrar(client, USUARIO_A)
    respuesta = client.post(f'/api/solicitudes/{original_id}/solicitar-ajuste', json={
        'titulo': 'Que también exporte a Excel',
        'descripcion': 'Lo necesito para cruzarlo con contabilidad',
        'urgencia_propuesta': 'Media',
    })
    assert respuesta.status_code == 201

    ajuste = respuesta.get_json()['solicitud']
    assert ajuste['id'] != original_id
    assert ajuste['estado'] == 'Por revisar'
    assert ajuste['relacionado_con_code'] is not None

    with app.app_context():
        from dev_tracker.models import DevTicket
        from extensions import db as _db
        original = _db.session.get(DevTicket, original_id)
        nuevo = _db.session.get(DevTicket, ajuste['id'])
        assert nuevo.relacionado_con_id == original_id
        assert nuevo.prioridad is None, 'la prioridad real la pone el desarrollador'
        assert nuevo.fecha_comprometida is None
        # El original ni se movió ni perdió su desenlace.
        assert original.estado == 'En Produccion'
        assert original.estado_plazo == 'entregado_a_tiempo'


def test_ajuste_no_ensucia_el_cumplimiento_del_original(client):
    """La métrica del original sigue en 100 % mientras el ajuste está en bandeja."""
    original_id = entregar(client)

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{original_id}/solicitar-ajuste',
                json={'titulo': 'Ahora con gráfico'})

    entrar(client, DEV_EMAIL)
    m = client.get('/api/dev-tracker/metrics').get_json()['metricas']
    assert m['entregados_total'] == 1
    assert m['pct_cumplimiento'] == 100.0
    assert m['total_activos'] == 0, 'el ajuste en bandeja aún no es trabajo activo'
    assert m['bandeja_pendiente'] == 1


def test_no_se_reporta_falla_sobre_algo_que_no_es_suyo(client):
    ticket_id = entregar(client)

    entrar(client, USUARIO_B)
    assert client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                       json={'descripcion': 'ajeno'}).status_code == 403
    assert client.post(f'/api/solicitudes/{ticket_id}/solicitar-ajuste',
                       json={'titulo': 'ajeno'}).status_code == 403


def test_no_se_reporta_falla_sobre_lo_que_aun_no_esta_listo(client):
    """Nada que probar todavía: el ticket sigue en la bandeja."""
    entrar(client, USUARIO_A)
    ticket_id = radicar(client).get_json()['solicitud']['id']

    respuesta = client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                            json={'descripcion': 'me falla'})
    assert respuesta.status_code == 409


def test_solicitante_ve_sus_propios_reportes(client):
    """Ve lo que él mismo escribió, no el detalle interno de errores."""
    ticket_id = entregar(client)

    entrar(client, USUARIO_A)
    client.post(f'/api/solicitudes/{ticket_id}/reportar-falla',
                json={'descripcion': 'El PDF sale en blanco'})

    # El desarrollador agrega un error interno suyo.
    entrar(client, DEV_EMAIL)
    client.post(f'/api/dev-tracker/tickets/{ticket_id}/bugs',
                json={'descripcion': 'Refactor del generador', 'severidad': 'Menor'})

    entrar(client, USUARIO_A)
    datos = client.get(f'/api/solicitudes/{ticket_id}').get_json()['solicitud']
    descripciones = [r['descripcion'] for r in datos['mis_reportes']]
    assert descripciones == ['El PDF sale en blanco']
    assert 'bugs' not in datos


def test_codigos_son_correlativos(client):
    entrar(client, DEV_EMAIL)
    codigos = []
    for i in range(3):
        codigos.append(client.post('/api/dev-tracker/tickets', json={
            'titulo': f'Ticket {i}', 'prioridad': 'Media'}).get_json()['ticket']['code'])
    assert codigos == ['DEV-001', 'DEV-002', 'DEV-003']

"""dev_tracker: tablas del modulo de tickets de desarrollo

Revision ID: d1c5a7b3e900
Revises: c7a2f1e83d40
Create Date: 2026-08-07 10:40:00.000000

Nota de convencion: los TIMESTAMP se guardan en UTC (igual que el resto del
repositorio). La conversion a hora de Bogota vive en dev_tracker/tiempo.py.
Las columnas DATE (fecha_comprometida, fecha_deseada) son fechas calendario
acordadas, no instantes, y no llevan zona horaria.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd1c5a7b3e900'
down_revision = 'e34d5d2e5a5f'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Tickets de desarrollo (idempotente)
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_tickets (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL UNIQUE,
            titulo VARCHAR(200) NOT NULL,
            descripcion TEXT,
            solicitante_nombre VARCHAR(150),
            solicitante_email VARCHAR(150),
            solicitante_area VARCHAR(150),
            origen VARCHAR(10) NOT NULL DEFAULT 'directo',
            urgencia_propuesta VARCHAR(10),
            fecha_deseada DATE,
            prioridad VARCHAR(10),
            estado VARCHAR(20) NOT NULL DEFAULT 'Por revisar',
            duplicado_de_id INTEGER REFERENCES dev_tickets(id),
            fecha_radicacion TIMESTAMP WITHOUT TIME ZONE,
            fecha_solicitud TIMESTAMP WITHOUT TIME ZONE,
            fecha_comprometida DATE,
            fecha_comprometida_original DATE,
            fecha_inicio_desarrollo TIMESTAMP WITHOUT TIME ZONE,
            fecha_entrada_pruebas TIMESTAMP WITHOUT TIME ZONE,
            fecha_salida_produccion TIMESTAMP WITHOUT TIME ZONE,
            notas_dev TEXT,
            creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_tickets_estado ON dev_tickets (estado);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_tickets_solicitante ON dev_tickets (solicitante_email);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_tickets_code ON dev_tickets (code);")

    # 2. Resoluciones de triage
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_triage_resolutions (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES dev_tickets(id) ON DELETE CASCADE,
            tipo VARCHAR(20) NOT NULL,
            comentario TEXT,
            fecha_resolucion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resuelto_por VARCHAR(150)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_triage_ticket ON dev_triage_resolutions (ticket_id);")

    # 3. Errores / bugs
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_ticket_bugs (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES dev_tickets(id) ON DELETE CASCADE,
            descripcion TEXT NOT NULL,
            severidad VARCHAR(10) NOT NULL DEFAULT 'Menor',
            etapa_deteccion VARCHAR(12) NOT NULL DEFAULT 'Pruebas',
            estado VARCHAR(10) NOT NULL DEFAULT 'Abierto',
            fecha_deteccion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_correccion TIMESTAMP WITHOUT TIME ZONE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_bugs_ticket ON dev_ticket_bugs (ticket_id);")

    # 4. Puntos de revision por ticket
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_ticket_checklists (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES dev_tickets(id) ON DELETE CASCADE,
            texto VARCHAR(300) NOT NULL,
            verificado BOOLEAN NOT NULL DEFAULT FALSE,
            fecha_verificacion TIMESTAMP WITHOUT TIME ZONE,
            orden INTEGER NOT NULL DEFAULT 0,
            es_personalizado BOOLEAN NOT NULL DEFAULT FALSE
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_checklist_ticket ON dev_ticket_checklists (ticket_id);")

    # 5. Historial de transiciones de estado
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_ticket_transitions (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER NOT NULL REFERENCES dev_tickets(id) ON DELETE CASCADE,
            estado_origen VARCHAR(20),
            estado_destino VARCHAR(20) NOT NULL,
            fecha_transicion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usuario_email VARCHAR(150)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dev_transitions_ticket ON dev_ticket_transitions (ticket_id);")

    # 6. Plantilla global de puntos de revision
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_checklist_templates (
            id SERIAL PRIMARY KEY,
            texto VARCHAR(300) NOT NULL,
            orden INTEGER NOT NULL DEFAULT 0,
            activo BOOLEAN NOT NULL DEFAULT TRUE
        );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS dev_checklist_templates;")
    op.execute("DROP TABLE IF EXISTS dev_ticket_transitions;")
    op.execute("DROP TABLE IF EXISTS dev_ticket_checklists;")
    op.execute("DROP TABLE IF EXISTS dev_ticket_bugs;")
    op.execute("DROP TABLE IF EXISTS dev_triage_resolutions;")
    op.execute("DROP TABLE IF EXISTS dev_tickets;")

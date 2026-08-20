"""dev_tracker: cola de correos y preferencias de aviso

Revision ID: f3a91d5e7c22
Revises: e2f7b19c4a11
Create Date: 2026-08-07 14:40:00.000000

dev_email_outbox hace tres trabajos a la vez:
  - cola: los correos no salen en la peticion web, se escriben aqui;
  - ventana para deshacer: programado_para deja 10 minutos de gracia y al
    enviar se vuelve a mirar si el aviso sigue siendo verdad;
  - registro anti-duplicados: un doble clic o un reinicio no reenvian nada.

dev_email_prefs guarda solo a quien APAGO los avisos. Ausencia de fila = activo,
para que nadie quede sin recibir por no haber entrado a configurar nada.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f3a91d5e7c22'
down_revision = 'e2f7b19c4a11'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_email_outbox (
            id SERIAL PRIMARY KEY,
            ticket_id INTEGER REFERENCES dev_tickets(id) ON DELETE CASCADE,
            bug_id INTEGER REFERENCES dev_ticket_bugs(id) ON DELETE CASCADE,
            evento VARCHAR(40) NOT NULL,
            destinatario VARCHAR(150) NOT NULL,
            programado_para TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            estado VARCHAR(12) NOT NULL DEFAULT 'pendiente',
            intentos INTEGER NOT NULL DEFAULT 0,
            ultimo_error TEXT,
            creado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            enviado_en TIMESTAMP WITHOUT TIME ZONE
        );
    """)
    # El trabajo del scheduler consulta por (estado, programado_para) cada 2 min.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dev_outbox_pendientes
        ON dev_email_outbox (estado, programado_para);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dev_outbox_dedup
        ON dev_email_outbox (ticket_id, evento, destinatario);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS dev_email_prefs (
            email VARCHAR(150) PRIMARY KEY,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            actualizado_en TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_dev_outbox_dedup;")
    op.execute("DROP INDEX IF EXISTS idx_dev_outbox_pendientes;")
    op.execute("DROP TABLE IF EXISTS dev_email_outbox;")
    op.execute("DROP TABLE IF EXISTS dev_email_prefs;")

"""dev_tracker: reporte de fallas y ajustes sobre lo ya entregado

Revision ID: e2f7b19c4a11
Revises: d1c5a7b3e900
Create Date: 2026-08-07 11:20:00.000000

Agrega lo necesario para los dos caminos de "ya lo entregaste, pero...":
  - dev_tickets.relacionado_con_id: un ajuste es un ticket NUEVO apuntando al
    original, no una reapertura, para no ensuciar la metrica de la entrega.
  - dev_ticket_bugs.reportado_por: quien reporto la falla desde el portal.
  - severidad pasa a VARCHAR(15) para admitir 'Sin clasificar', el estado de una
    falla reportada que el desarrollador aun no ha evaluado.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e2f7b19c4a11'
down_revision = 'd1c5a7b3e900'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE dev_tickets
        ADD COLUMN IF NOT EXISTS relacionado_con_id INTEGER REFERENCES dev_tickets(id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dev_tickets_relacionado
        ON dev_tickets (relacionado_con_id);
    """)
    op.execute("""
        ALTER TABLE dev_ticket_bugs
        ADD COLUMN IF NOT EXISTS reportado_por VARCHAR(150);
    """)
    # 'Sin clasificar' son 15 caracteres; la columna nacio con 10.
    op.execute("""
        ALTER TABLE dev_ticket_bugs
        ALTER COLUMN severidad TYPE VARCHAR(15);
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_dev_tickets_relacionado;")
    op.execute("ALTER TABLE dev_tickets DROP COLUMN IF EXISTS relacionado_con_id;")
    op.execute("ALTER TABLE dev_ticket_bugs DROP COLUMN IF EXISTS reportado_por;")
    # Las filas 'Sin clasificar' no caben en VARCHAR(10): se normalizan a 'Menor'
    # antes de encoger la columna, si no el ALTER falla.
    op.execute("""
        UPDATE dev_ticket_bugs SET severidad = 'Menor'
        WHERE severidad = 'Sin clasificar';
    """)
    op.execute("ALTER TABLE dev_ticket_bugs ALTER COLUMN severidad TYPE VARCHAR(10);")

"""add asesor pending fields to solicitudes_cita

Revision ID: 8c9d4f1f3b2b
Revises: f6180b18085b
Create Date: 2025-11-06 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8c9d4f1f3b2b'
down_revision = 'f6180b18085b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'solicitudes_cita',
        sa.Column('asesor_pendiente', sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        'solicitudes_cita',
        sa.Column('asesor_pendiente_desde', sa.DateTime(), nullable=True)
    )
    op.alter_column('solicitudes_cita', 'asesor_pendiente', server_default=None)


def downgrade():
    op.drop_column('solicitudes_cita', 'asesor_pendiente_desde')
    op.drop_column('solicitudes_cita', 'asesor_pendiente')

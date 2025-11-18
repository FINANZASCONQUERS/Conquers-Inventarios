"""Add pending location fields

Revision ID: 1b9c1f3c4e2b
Revises: 4768f938892c
Create Date: 2025-11-07 15:32:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b9c1f3c4e2b'
down_revision = '4768f938892c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('solicitudes_cita', sa.Column('ubicacion_pendiente_lat', sa.Float(), nullable=True))
    op.add_column('solicitudes_cita', sa.Column('ubicacion_pendiente_lng', sa.Float(), nullable=True))
    op.add_column('solicitudes_cita', sa.Column('ubicacion_pendiente_tipo', sa.String(length=32), nullable=True))
    op.add_column('solicitudes_cita', sa.Column('ubicacion_pendiente_mensaje', sa.String(length=255), nullable=True))
    op.add_column('solicitudes_cita', sa.Column('ubicacion_pendiente_desde', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('solicitudes_cita', 'ubicacion_pendiente_desde')
    op.drop_column('solicitudes_cita', 'ubicacion_pendiente_mensaje')
    op.drop_column('solicitudes_cita', 'ubicacion_pendiente_tipo')
    op.drop_column('solicitudes_cita', 'ubicacion_pendiente_lng')
    op.drop_column('solicitudes_cita', 'ubicacion_pendiente_lat')

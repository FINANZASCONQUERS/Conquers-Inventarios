"""Allow repeated turn numbers per day

Revision ID: aad4d8fdc2cf
Revises: 485c3f0848fc
Create Date: 2025-11-11 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aad4d8fdc2cf'
down_revision = '485c3f0848fc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('solicitudes_cita', schema=None) as batch_op:
        batch_op.drop_constraint('solicitudes_cita_turno_key', type_='unique')
        batch_op.add_column(sa.Column('turno_fecha', sa.Date(), nullable=True))

    op.execute(
        """
        UPDATE solicitudes_cita
        SET turno_fecha = DATE(fecha_descargue)
        WHERE turno IS NOT NULL AND fecha_descargue IS NOT NULL
        """
    )

    with op.batch_alter_table('solicitudes_cita', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_solicitudes_turno_fecha', ['turno_fecha', 'turno'])


def downgrade():
    with op.batch_alter_table('solicitudes_cita', schema=None) as batch_op:
        batch_op.drop_constraint('uq_solicitudes_turno_fecha', type_='unique')

    op.execute("UPDATE solicitudes_cita SET turno_fecha = NULL")

    with op.batch_alter_table('solicitudes_cita', schema=None) as batch_op:
        batch_op.drop_column('turno_fecha')
        batch_op.create_unique_constraint('solicitudes_cita_turno_key', ['turno'])

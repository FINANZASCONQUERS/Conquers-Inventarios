"""Add remolque y celular a conductores"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4f0f6f8b5e31'
down_revision = '4768f938892c'
branch_labels = None
depends_on = None


def upgrade():
	with op.batch_alter_table('conductores', schema=None) as batch_op:
		batch_op.add_column(sa.Column('placa_remolque', sa.String(length=64), nullable=True))
		batch_op.add_column(sa.Column('celular', sa.String(length=32), nullable=True))


def downgrade():
	with op.batch_alter_table('conductores', schema=None) as batch_op:
		batch_op.drop_column('celular')
		batch_op.drop_column('placa_remolque')

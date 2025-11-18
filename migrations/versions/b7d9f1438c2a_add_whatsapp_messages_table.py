"""Create WhatsApp message log table

Revision ID: b7d9f1438c2a
Revises: 1a4c94f2174e
Create Date: 2025-11-05 16:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d9f1438c2a'
down_revision = '1a4c94f2174e'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.dialect.has_table(bind, 'whatsapp_messages'):
        op.create_table(
            'whatsapp_messages',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('solicitud_id', sa.Integer(), sa.ForeignKey('solicitudes_cita.id'), nullable=True),
            sa.Column('telefono', sa.String(length=32), nullable=False),
            sa.Column('direction', sa.String(length=16), nullable=False),
            sa.Column('sender', sa.String(length=16), nullable=False),
            sa.Column('message_type', sa.String(length=32), nullable=False, server_default='text'),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('media_url', sa.String(length=512), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now())
        )
        op.create_index('ix_whatsapp_messages_telefono', 'whatsapp_messages', ['telefono'])
        op.create_index('ix_whatsapp_messages_created_at', 'whatsapp_messages', ['created_at'])


def downgrade():
    bind = op.get_bind()
    if bind.dialect.has_table(bind, 'whatsapp_messages'):
        op.drop_index('ix_whatsapp_messages_created_at', table_name='whatsapp_messages')
        op.drop_index('ix_whatsapp_messages_telefono', table_name='whatsapp_messages')
        op.drop_table('whatsapp_messages')

"""
Revision ID: add_guia_fields_turno_carro
Revises: 
Create Date: 2025-10-27
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('turnos_carro', sa.Column('guia_enturnamiento', sa.String(length=256)))
    op.add_column('turnos_carro', sa.Column('guia_programacion_cargue', sa.String(length=256)))

def downgrade():
    op.drop_column('turnos_carro', 'guia_enturnamiento')
    op.drop_column('turnos_carro', 'guia_programacion_cargue')

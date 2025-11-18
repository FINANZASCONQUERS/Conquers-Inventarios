"""merge heads after conductor fields

Revision ID: 485c3f0848fc
Revises: 1b9c1f3c4e2b, 4f0f6f8b5e31
Create Date: 2025-11-10 08:08:21.534157

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '485c3f0848fc'
down_revision = ('1b9c1f3c4e2b', '4f0f6f8b5e31')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

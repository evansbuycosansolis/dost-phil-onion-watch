"""initial schema

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op

from app.core.database import Base
from app.models import *  # noqa: F401,F403

# revision identifiers, used by Alembic.
revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)

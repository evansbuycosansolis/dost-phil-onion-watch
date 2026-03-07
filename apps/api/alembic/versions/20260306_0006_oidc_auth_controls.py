"""oidc auth controls and mfa tracking fields on users

Revision ID: 20260306_0006
Revises: 20260306_0005
Create Date: 2026-03-06 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260306_0006"
down_revision = "20260306_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("auth_provider", sa.String(length=40), nullable=False, server_default="local"))
        batch_op.add_column(sa.Column("oidc_subject", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("last_mfa_verified_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_users_oidc_subject", ["oidc_subject"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_oidc_subject")
        batch_op.drop_column("last_mfa_verified_at")
        batch_op.drop_column("oidc_subject")
        batch_op.drop_column("auth_provider")

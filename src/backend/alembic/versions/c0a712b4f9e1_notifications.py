"""notifications table

Revision ID: c0a712b4f9e1
Revises: 8ebb35ef208a
Create Date: 2026-06-07 12:00:00.000000

Adds the per-user notification feed. One row per (recipient, event), read_at
null until the user marks it as read. Index on (user_id, created_at) so the
"newest first + unread count" queries are O(log n).
"""
from alembic import op
import sqlalchemy as sa


revision = "c0a712b4f9e1"
down_revision = "8ebb35ef208a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification",
        sa.Column("id",         sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("user_id",    sa.Integer(),     nullable=False),
        sa.Column("kind",       sa.String(50),    nullable=False),
        sa.Column("title",      sa.String(200),   nullable=False),
        sa.Column("body",       sa.String(500),   nullable=True),
        sa.Column("link",       sa.String(255),   nullable=True),
        sa.Column("created_at", sa.DateTime(),    nullable=False),
        sa.Column("read_at",    sa.DateTime(),    nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"],
            name="fk_notification_user",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_notification_user_created", "notification",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_user_created", table_name="notification")
    op.drop_table("notification")

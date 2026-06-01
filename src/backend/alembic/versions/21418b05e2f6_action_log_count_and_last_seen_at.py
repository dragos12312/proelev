"""action_log count and last_seen_at

Revision ID: 21418b05e2f6
Revises: 321d12829f3f
Create Date: 2026-05-04 19:10:01.372129

"""
from alembic import op
import sqlalchemy as sa


revision = '21418b05e2f6'
down_revision = '321d12829f3f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # add count with a server side default so existing rows backfill to 1,
    # then drop the default so future inserts must specify it explicitly
    # last_seen_at is nullable, we backfill it to created_at for existing rows
    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('count', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_action_log_user_last_seen', ['user_id', 'last_seen_at'], unique=False)

    # backfill last_seen_at = created_at on existing rows
    op.execute("UPDATE action_log SET last_seen_at = created_at WHERE last_seen_at IS NULL")

    # drop the temporary server default for count
    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.alter_column('count', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('action_log', schema=None) as batch_op:
        batch_op.drop_index('ix_action_log_user_last_seen')
        batch_op.drop_column('last_seen_at')
        batch_op.drop_column('count')

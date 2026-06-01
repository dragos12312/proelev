"""hash password and rename column

Revision ID: 19b052b1c739
Revises: 21418b05e2f6
Create Date: 2026-05-15 11:06:24.947297

Adds a new bcrypt-backed password_hash column on the user table, rehashes
any existing plain-text passwords, then drops the old plain column.
"""
from alembic import op
import sqlalchemy as sa
from passlib.context import CryptContext


revision = '19b052b1c739'
down_revision = '21418b05e2f6'
branch_labels = None
depends_on = None


_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def upgrade() -> None:
    # add the new column as nullable so we can backfill from the old column
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))

    # backfill: rehash every existing plain-text password
    bind = op.get_bind()
    rows = list(bind.execute(sa.text("SELECT id, password FROM user")))
    for r in rows:
        h = _pwd_ctx.hash(r.password or "")
        bind.execute(
            sa.text("UPDATE user SET password_hash = :h WHERE id = :id"),
            {"h": h, "id": r.id},
        )

    # now drop the old column and make password_hash required
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('password')
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    # we cant recover the plaintext, so downgrade just adds the column back empty
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password', sa.String(length=150), nullable=False, server_default=""))
        batch_op.drop_column('password_hash')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password', server_default=None)

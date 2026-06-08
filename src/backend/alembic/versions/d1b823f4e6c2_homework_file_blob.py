"""homework file_blob

Revision ID: d1b823f4e6c2
Revises: c0a712b4f9e1
Create Date: 2026-06-08 10:00:00.000000

Adds Homework.file_blob (LargeBinary) so the teacher's attached PDF/image
survives Render's ephemeral filesystem. file_name was always there but the
bytes were never stored.
"""
from alembic import op
import sqlalchemy as sa


revision = "d1b823f4e6c2"
down_revision = "c0a712b4f9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("homework") as batch:
        batch.add_column(sa.Column("file_blob", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("homework") as batch:
        batch.drop_column("file_blob")

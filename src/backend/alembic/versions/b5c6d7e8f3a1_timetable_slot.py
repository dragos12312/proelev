"""timetable_slot table

Revision ID: b5c6d7e8f3a1
Revises: a4b8c2d3e91f
Create Date: 2026-06-09 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f3a1"
down_revision = "a4b8c2d3e91f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timetable_slot",
        sa.Column("id",              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("class_id",        sa.Integer(), nullable=False),
        sa.Column("subject_id",      sa.Integer(), nullable=False),
        sa.Column("teacher_user_id", sa.Integer(), nullable=True),
        sa.Column("day",             sa.Integer(), nullable=False),
        sa.Column("period",          sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["class_id"],        ["school_class.id"], name="fk_tt_class",   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"],      ["subject.id"],      name="fk_tt_subject", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_user_id"], ["user.id"],         name="fk_tt_teacher", ondelete="SET NULL"),
        sa.UniqueConstraint("class_id", "day", "period", name="uq_timetable_slot_class_day_period"),
    )
    op.create_index("ix_timetable_slot_class_day", "timetable_slot", ["class_id", "day"])


def downgrade() -> None:
    op.drop_index("ix_timetable_slot_class_day", table_name="timetable_slot")
    op.drop_table("timetable_slot")

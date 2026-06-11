"""behavior_grade and school_announcement tables

Revision ID: a4b8c2d3e91f
Revises: f3d5e6a7c91a
Create Date: 2026-06-09 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a4b8c2d3e91f"
down_revision = "f3d5e6a7c91a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "behavior_grade",
        sa.Column("id",                 sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("student_user_id",    sa.Integer(),  nullable=False),
        sa.Column("period",             sa.String(64), nullable=False),
        sa.Column("grade",              sa.Integer(),  nullable=False),
        sa.Column("note",               sa.Text(),     nullable=True),
        sa.Column("created_by_user_id", sa.Integer(),  nullable=True),
        sa.Column("created_at",         sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_user_id"],    ["user.id"], name="fk_behavior_student", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], name="fk_behavior_creator", ondelete="SET NULL"),
        sa.UniqueConstraint("student_user_id", "period", name="uq_behavior_grade_student_period"),
        sa.CheckConstraint("grade >= 1 AND grade <= 10", name="ck_behavior_grade_range"),
    )

    op.create_table(
        "school_announcement",
        sa.Column("id",                 sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("title",              sa.String(200), nullable=False),
        sa.Column("body",               sa.Text(),     nullable=True),
        sa.Column("kind",               sa.String(20), nullable=False, server_default="info"),
        sa.Column("created_by_user_id", sa.Integer(),  nullable=True),
        sa.Column("created_at",         sa.DateTime(), nullable=False),
        sa.Column("pinned",             sa.Integer(),  nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], name="fk_school_ann_creator", ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("school_announcement")
    op.drop_table("behavior_grade")

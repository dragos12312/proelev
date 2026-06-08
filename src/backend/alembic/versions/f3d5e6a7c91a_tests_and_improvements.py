"""tests, test_grade, test_improvement tables

Revision ID: f3d5e6a7c91a
Revises: e2c934a5b1d8
Create Date: 2026-06-08 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f3d5e6a7c91a"
down_revision = "e2c934a5b1d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test",
        sa.Column("id",             sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("class_id",       sa.Integer(),     nullable=False),
        sa.Column("subject_id",     sa.Integer(),     nullable=False),
        sa.Column("title",          sa.String(200),   nullable=False),
        sa.Column("description",    sa.Text(),        nullable=True),
        sa.Column("scheduled_date", sa.Date(),        nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at",     sa.DateTime(),    nullable=False),
        sa.ForeignKeyConstraint(["class_id"],           ["school_class.id"], name="fk_test_class",   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"],         ["subject.id"],      name="fk_test_subject", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"],         name="fk_test_creator", ondelete="SET NULL"),
    )
    op.create_index("ix_test_class_subject_date", "test", ["class_id", "subject_id", "scheduled_date"])

    op.create_table(
        "test_grade",
        sa.Column("id",                sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("test_id",           sa.Integer(),  nullable=False),
        sa.Column("student_user_id",   sa.Integer(),  nullable=False),
        sa.Column("grade",             sa.Integer(),  nullable=True),
        sa.Column("feedback",          sa.Text(),     nullable=True),
        sa.Column("graded_by_user_id", sa.Integer(),  nullable=True),
        sa.Column("graded_at",         sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["test_id"],           ["test.id"], name="fk_test_grade_test",    ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_user_id"],   ["user.id"], name="fk_test_grade_student", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graded_by_user_id"], ["user.id"], name="fk_test_grade_grader",  ondelete="SET NULL"),
        sa.UniqueConstraint("test_id", "student_user_id", name="uq_test_grade_test_student"),
        sa.CheckConstraint("grade IS NULL OR (grade >= 1 AND grade <= 10)", name="ck_test_grade_range"),
    )
    op.create_index("ix_test_grade_student", "test_grade", ["student_user_id"])

    op.create_table(
        "test_improvement",
        sa.Column("id",               sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("student_user_id",  sa.Integer(),  nullable=False),
        sa.Column("subject_id",       sa.Integer(),  nullable=False),
        sa.Column("previous_test_id", sa.Integer(),  nullable=True),
        sa.Column("new_test_id",      sa.Integer(),  nullable=False),
        sa.Column("old_grade",        sa.Integer(),  nullable=False),
        sa.Column("new_grade",        sa.Integer(),  nullable=False),
        sa.Column("created_at",       sa.DateTime(), nullable=False),
        sa.Column("ack_at",           sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["student_user_id"],  ["user.id"],    name="fk_test_imp_student", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"],       ["subject.id"], name="fk_test_imp_subject", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_test_id"], ["test.id"],    name="fk_test_imp_prev",    ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["new_test_id"],      ["test.id"],    name="fk_test_imp_new",     ondelete="CASCADE"),
    )
    op.create_index("ix_test_improvement_student_ack", "test_improvement", ["student_user_id", "ack_at"])


def downgrade() -> None:
    op.drop_index("ix_test_improvement_student_ack", table_name="test_improvement")
    op.drop_table("test_improvement")
    op.drop_index("ix_test_grade_student", table_name="test_grade")
    op.drop_table("test_grade")
    op.drop_index("ix_test_class_subject_date", table_name="test")
    op.drop_table("test")

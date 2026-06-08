"""attendance and subject channel tables

Revision ID: e2c934a5b1d8
Revises: d1b823f4e6c2
Create Date: 2026-06-08 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "e2c934a5b1d8"
down_revision = "d1b823f4e6c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attendance",
        sa.Column("id",                 sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("class_id",           sa.Integer(),     nullable=False),
        sa.Column("student_user_id",    sa.Integer(),     nullable=False),
        sa.Column("date",               sa.Date(),        nullable=False),
        sa.Column("status",             sa.String(20),    nullable=False),
        sa.Column("note",               sa.String(255),   nullable=True),
        sa.Column("created_by_user_id", sa.Integer(),     nullable=True),
        sa.Column("created_at",         sa.DateTime(),    nullable=False),
        sa.ForeignKeyConstraint(["class_id"],           ["school_class.id"], name="fk_attendance_class",   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_user_id"],    ["user.id"],         name="fk_attendance_student", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"],         name="fk_attendance_creator", ondelete="SET NULL"),
        sa.UniqueConstraint("class_id", "student_user_id", "date", name="uq_attendance_class_student_date"),
    )
    op.create_index("ix_attendance_class_date",   "attendance", ["class_id", "date"])
    op.create_index("ix_attendance_student_date", "attendance", ["student_user_id", "date"])

    op.create_table(
        "subject_channel_post",
        sa.Column("id",             sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("class_id",       sa.Integer(),     nullable=False),
        sa.Column("subject_id",     sa.Integer(),     nullable=False),
        sa.Column("author_user_id", sa.Integer(),     nullable=True),
        sa.Column("kind",           sa.String(10),    nullable=False),
        sa.Column("text",           sa.Text(),        nullable=True),
        sa.Column("file_name",      sa.String(255),   nullable=True),
        sa.Column("file_blob",      sa.LargeBinary(), nullable=True),
        sa.Column("created_at",     sa.DateTime(),    nullable=False),
        sa.ForeignKeyConstraint(["class_id"],       ["school_class.id"], name="fk_channel_post_class",   ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"],     ["subject.id"],      name="fk_channel_post_subject", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["user.id"],         name="fk_channel_post_author",  ondelete="SET NULL"),
    )
    op.create_index("ix_channel_post_channel_created", "subject_channel_post", ["class_id", "subject_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_channel_post_channel_created", table_name="subject_channel_post")
    op.drop_table("subject_channel_post")
    op.drop_index("ix_attendance_student_date", table_name="attendance")
    op.drop_index("ix_attendance_class_date",   table_name="attendance")
    op.drop_table("attendance")

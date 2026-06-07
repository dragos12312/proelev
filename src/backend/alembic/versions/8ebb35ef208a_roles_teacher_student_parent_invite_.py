"""roles teacher student parent invite codes submissions

Revision ID: 8ebb35ef208a
Revises: 7cfc4d9b5eab
Create Date: 2026-06-06 13:24:09.883768

Assignment 6 schema additions:
- invite_code: admin-generated codes that gate the teacher/student/parent
  self-register flow. 7 day TTL, single use.
- teacher_assignment: M2M of (teacher, class, subject) pairs.
- parent_child: M2M linking parent users to child users.
- user.class_id: which class a student user belongs to.
- homework.created_by_user_id: which teacher posted it.
- student: now also a submission record with file/text/feedback fields.

The existing ix_student_grade and ix_student_tag_tag indices are intentionally
kept; alembic's autogen wanted to drop them because they were added imperatively
in migration 7cfc4d9b5eab rather than via SQLAlchemy column metadata.
"""
from alembic import op
import sqlalchemy as sa


revision = '8ebb35ef208a'
down_revision = '7cfc4d9b5eab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'invite_code',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('role_name', sa.String(length=50), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=True),
        sa.Column('subject_id', sa.Integer(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('used_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['class_id'], ['school_class.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_invite_code_code', 'invite_code', ['code'])

    op.create_table(
        'parent_child',
        sa.Column('parent_user_id', sa.Integer(), nullable=False),
        sa.Column('child_user_id',  sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['parent_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['child_user_id'],  ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('parent_user_id', 'child_user_id'),
    )

    op.create_table(
        'teacher_assignment',
        sa.Column('user_id',    sa.Integer(), nullable=False),
        sa.Column('class_id',   sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'],    ['user.id'],         ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['class_id'],   ['school_class.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.id'],      ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'class_id', 'subject_id'),
    )

    with op.batch_alter_table('homework', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_homework_created_by_user',
            'user', ['created_by_user_id'], ['id'], ondelete='SET NULL',
        )

    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id',              sa.Integer(),     nullable=True))
        batch_op.add_column(sa.Column('submitted_at',         sa.DateTime(),    nullable=True))
        batch_op.add_column(sa.Column('submission_text',      sa.Text(),        nullable=True))
        batch_op.add_column(sa.Column('submission_file_name', sa.String(255),   nullable=True))
        batch_op.add_column(sa.Column('submission_blob',      sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('feedback',             sa.Text(),        nullable=True))
        batch_op.create_foreign_key(
            'fk_student_user', 'user', ['user_id'], ['id'], ondelete='SET NULL',
        )

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('class_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_user_class', 'school_class', ['class_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_class', type_='foreignkey')
        batch_op.drop_column('class_id')

    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.drop_constraint('fk_student_user', type_='foreignkey')
        batch_op.drop_column('feedback')
        batch_op.drop_column('submission_blob')
        batch_op.drop_column('submission_file_name')
        batch_op.drop_column('submission_text')
        batch_op.drop_column('submitted_at')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('homework', schema=None) as batch_op:
        batch_op.drop_constraint('fk_homework_created_by_user', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')

    op.drop_table('teacher_assignment')
    op.drop_table('parent_child')
    op.drop_index('ix_invite_code_code', table_name='invite_code')
    op.drop_table('invite_code')

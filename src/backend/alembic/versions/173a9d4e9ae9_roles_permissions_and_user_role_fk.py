"""roles permissions and user role fk

Revision ID: 173a9d4e9ae9
Revises: b3cd54ae3df4
Create Date: 2026-05-02 15:14:20.170075

"""
from alembic import op
import sqlalchemy as sa


revision = '173a9d4e9ae9'
down_revision = 'b3cd54ae3df4'
branch_labels = None
depends_on = None


# canonical role/permission setup, kept inline so the migration is self-contained
# and works on machines that don't yet import models.py
PERMISSIONS = [
    "homework_read", "homework_create", "homework_update", "homework_delete",
    "student_read",  "student_create",  "student_update",  "student_delete",
    "comment_read",  "comment_create",  "comment_update",  "comment_delete",
    "stats_read",
    "chat_read",     "chat_send",
]
ROLE_PERMISSIONS = {
    "admin": PERMISSIONS,
    "user": [
        "homework_read", "student_read",
        "comment_read",  "comment_create",
        "stats_read",
        "chat_read",     "chat_send",
    ],
}


def upgrade() -> None:
    # ── new tables ───────────────────────────────────────────────────────────
    permission_t = op.create_table('permission',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=80), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    role_t = op.create_table('role',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    role_permission_t = op.create_table('role_permission',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permission.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    # ── seed the canonical permissions and roles inside the migration ───────
    # so user.role_id has something safe to point at when we add it
    op.bulk_insert(permission_t, [{"code": c} for c in PERMISSIONS])
    op.bulk_insert(role_t, [{"name": r} for r in ROLE_PERMISSIONS.keys()])

    bind = op.get_bind()
    perm_ids = {row[1]: row[0] for row in bind.execute(sa.text("SELECT id, code FROM permission"))}
    role_ids = {row[1]: row[0] for row in bind.execute(sa.text("SELECT id, name FROM role"))}

    rp_rows = []
    for role_name, codes in ROLE_PERMISSIONS.items():
        rid = role_ids[role_name]
        for code in codes:
            rp_rows.append({"role_id": rid, "permission_id": perm_ids[code]})
    if rp_rows:
        op.bulk_insert(role_permission_t, rp_rows)

    admin_role_id = role_ids["admin"]

    # ── add user.role_id with admin as the temporary default ─────────────────
    # backfill any existing rows, then drop the server default so future
    # inserts are forced to specify a role explicitly
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'role_id', sa.Integer(),
            nullable=False, server_default=str(admin_role_id),
        ))
        batch_op.create_foreign_key(
            'fk_user_role', 'role',
            ['role_id'], ['id'], ondelete='RESTRICT',
        )
    # drop the temporary default now that backfill is done
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('role_id', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_role', type_='foreignkey')
        batch_op.drop_column('role_id')

    op.drop_table('role_permission')
    op.drop_table('role')
    op.drop_table('permission')

"""calendar feeds

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 16:09:03.044820
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('calendar_feeds',
    sa.Column('url_enc', sa.Text(), nullable=False),
    sa.Column('host', sa.String(length=200), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('stats', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_calendar_feeds_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendar_feeds'))
    )
    with op.batch_alter_table('calendar_feeds', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_feeds_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_uid', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('due_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_assignments_external_uid'), ['external_uid'], unique=False)

    with op.batch_alter_table('exams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_uid', sa.String(length=300), nullable=True))
        batch_op.create_index(batch_op.f('ix_exams_external_uid'), ['external_uid'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('exams', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_exams_external_uid'))
        batch_op.drop_column('external_uid')

    with op.batch_alter_table('assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_assignments_external_uid'))
        batch_op.drop_column('due_at')
        batch_op.drop_column('external_uid')

    with op.batch_alter_table('calendar_feeds', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_feeds_user_id'))

    op.drop_table('calendar_feeds')

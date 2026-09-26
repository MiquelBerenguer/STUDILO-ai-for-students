"""cards, agent actions, guest users

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 15:05:23.453825
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('agent_actions',
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('risk', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('effects', sa.JSON(), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('upload_id', sa.String(length=36), nullable=True),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['upload_id'], ['uploads.id'], name=op.f('fk_agent_actions_upload_id_uploads'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_agent_actions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_actions'))
    )
    with op.batch_alter_table('agent_actions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_actions_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_actions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_actions_user_id'), ['user_id'], unique=False)

    # v1 notifications become feed cards; existing rows keep working (status 'open' for unread, 'done' for read).
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=16), nullable=False, server_default='open'))
        batch_op.add_column(sa.Column('actions', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('priority', sa.Integer(), nullable=False, server_default='50'))
        batch_op.add_column(sa.Column('dedupe_key', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('action_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('course_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('resolved_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_notifications_status'), ['status'], unique=False)
        batch_op.create_unique_constraint('uq_notifications_user_dedupe', ['user_id', 'dedupe_key'])
        batch_op.create_foreign_key(batch_op.f('fk_notifications_course_id_courses'), 'courses', ['course_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(batch_op.f('fk_notifications_action_id_agent_actions'), 'agent_actions', ['action_id'], ['id'], ondelete='SET NULL')
    op.execute("UPDATE notifications SET status = 'done' WHERE read_at IS NOT NULL")

    # Guest users (onboarding before registration): email / password become optional.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('email', existing_type=sa.VARCHAR(length=320), nullable=True)
        batch_op.alter_column('password_hash', existing_type=sa.VARCHAR(length=100), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email IS NULL")
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('password_hash', existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.alter_column('email', existing_type=sa.VARCHAR(length=320), nullable=False)
        batch_op.drop_column('last_seen_at')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_notifications_action_id_agent_actions'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_notifications_course_id_courses'), type_='foreignkey')
        batch_op.drop_constraint('uq_notifications_user_dedupe', type_='unique')
        batch_op.drop_index(batch_op.f('ix_notifications_status'))
        for col in ('resolved_at', 'course_id', 'action_id', 'dedupe_key', 'priority', 'actions', 'status'):
            batch_op.drop_column(col)
    with op.batch_alter_table('agent_actions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_actions_user_id'))
        batch_op.drop_index(batch_op.f('ix_agent_actions_status'))
        batch_op.drop_index(batch_op.f('ix_agent_actions_job_id'))
    op.drop_table('agent_actions')

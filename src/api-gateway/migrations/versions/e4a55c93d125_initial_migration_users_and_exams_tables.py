"""Initial migration: users and exams tables

Revision ID: e4a55c93d125 (tu ID puede variar, no importa)
Revises: 
Create Date: 2025-12-24 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4a55c93d125' # ¡OJO! Asegúrate que este ID coincide con el nombre de tu archivo
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------
    # 1. CREACIÓN DE LA NUEVA ARQUITECTURA (Usuarios)
    # -----------------------------------------------------------
    op.create_table('users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # -----------------------------------------------------------
    # 2. ZONA DE PROTECCIÓN (NO BORRAR NADA ANTIGUO)
    # He puesto '#' delante de todo lo que Alembic quería destruir.
    # -----------------------------------------------------------
    # op.drop_index(op.f('idx_patterns_lookup'), table_name='pedagogical_patterns')
    # op.drop_table('pedagogical_patterns')
    # op.drop_table('study_sessions')
    # op.drop_table('study_plan_items')
    # op.drop_table('material_topics')
    # op.drop_index(op.f('idx_topics_course'), table_name='topics')
    # op.drop_table('topics')
    # op.drop_table('topic_mastery')
    # op.drop_table('course_materials')
    # op.drop_table('study_plans')
    # op.drop_table('exam_questions')
    # op.drop_table('courses')
    # op.drop_table('students')

    # -----------------------------------------------------------
    # 3. ACTUALIZACIÓN HÍBRIDA DE LA TABLA 'EXAMS'
    # Añadimos lo nuevo, pero mantenemos lo viejo por si acaso.
    # -----------------------------------------------------------
    
    # -- Añadir columnas nuevas --
    op.add_column('exams', sa.Column('user_id', sa.UUID(), nullable=True)) # Nullable true temporalmente para no romper datos viejos
    op.add_column('exams', sa.Column('topic', sa.String(), nullable=True))
    op.add_column('exams', sa.Column('difficulty', sa.String(), nullable=True))
    op.add_column('exams', sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('exams', sa.Column('result_url', sa.String(), nullable=True))
    op.add_column('exams', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('exams', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # -- Índices nuevos --
    op.create_index(op.f('ix_exams_created_at'), 'exams', ['created_at'], unique=False)
    op.create_index(op.f('ix_exams_status'), 'exams', ['status'], unique=False)
    op.create_index(op.f('ix_exams_user_id'), 'exams', ['user_id'], unique=False)

    # -- Crear relación con la nueva tabla Users --
    op.create_foreign_key(None, 'exams', 'users', ['user_id'], ['id'])

    # -- PROTECCIÓN DE COLUMNAS ANTIGUAS EN EXAMS --
    # Comentamos los 'drop' para no perder info de cursos antiguos
    # op.drop_constraint('exams_course_id_fkey', 'exams', type_='foreignkey')
    # op.drop_column('exams', 'course_id')
    # op.drop_column('exams', 'title')
    # op.drop_column('exams', 'scope_type')
    # op.drop_column('exams', 'score_average')
    # op.drop_column('exams', 'topics_included')


def downgrade() -> None:
    # Esta función deshace los cambios si algo sale mal.
    # No es crítica ahora, pero la dejo correcta.
    op.drop_constraint(None, 'exams', type_='foreignkey')
    op.drop_index(op.f('ix_exams_user_id'), table_name='exams')
    op.drop_index(op.f('ix_exams_status'), table_name='exams')
    op.drop_index(op.f('ix_exams_created_at'), table_name='exams')
    op.drop_column('exams', 'updated_at')
    op.drop_column('exams', 'error_message')
    op.drop_column('exams', 'result_url')
    op.drop_column('exams', 'content')
    op.drop_column('exams', 'difficulty')
    op.drop_column('exams', 'topic')
    op.drop_column('exams', 'user_id')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')

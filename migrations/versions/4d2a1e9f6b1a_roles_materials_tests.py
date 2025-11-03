"""
roles + materials + tests engine

Revision ID: 4d2a1e9f6b1a
Revises: 
Create Date: 2025-11-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import String


# revision identifiers, used by Alembic.
revision = '4d2a1e9f6b1a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # user.role
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=20), nullable=False, server_default='admin'))

    # student.user_id
    with op.batch_alter_table('student') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(None, 'user', ['user_id'], ['id'])

    # materials
    op.create_table(
        'material',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('course.id'), nullable=False),
        sa.Column('file_path', sa.String(length=300), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # tests engine
    op.create_table(
        'test',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('course.id'), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'question',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('test_id', sa.Integer(), sa.ForeignKey('test.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
    )

    op.create_table(
        'option',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('question.id'), nullable=False),
        sa.Column('text', sa.String(length=500), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        'attempt',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('test_id', sa.Integer(), sa.ForeignKey('test.id'), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('student.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True, server_default='0'),
    )

    op.create_table(
        'attempt_answer',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('attempt_id', sa.Integer(), sa.ForeignKey('attempt.id'), nullable=False),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('question.id'), nullable=False),
        sa.Column('option_id', sa.Integer(), sa.ForeignKey('option.id'), nullable=False),
    )


def downgrade():
    op.drop_table('attempt_answer')
    op.drop_table('attempt')
    op.drop_table('option')
    op.drop_table('question')
    op.drop_table('test')
    op.drop_table('material')

    with op.batch_alter_table('student') as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('role')


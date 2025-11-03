"""
add student.access_code

Revision ID: 9a1e0c3b2c7a
Revises: 4d2a1e9f6b1a
Create Date: 2025-11-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '9a1e0c3b2c7a'
down_revision = '4d2a1e9f6b1a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('student') as batch_op:
        batch_op.add_column(sa.Column('access_code', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint('uq_student_access_code', ['access_code'])


def downgrade():
    with op.batch_alter_table('student') as batch_op:
        batch_op.drop_constraint('uq_student_access_code', type_='unique')
        batch_op.drop_column('access_code')


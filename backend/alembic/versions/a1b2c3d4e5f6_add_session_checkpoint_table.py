"""Add session_checkpoint table for long-term workflow recovery

Revision ID: a1b2c3d4e5f6
Revises: d46240a71273
Create Date: 2026-02-27 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd46240a71273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_checkpoint table and W9/WAITING_DIRECTION support."""
    op.create_table(
        'session_checkpoint',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('workflow_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('step_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('agent_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='completed'),
        sa.Column('agent_output', sa.JSON(), nullable=True),
        sa.Column('cost_incurred', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('idempotency_token', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('user_adjustment', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_session_checkpoint_workflow_id'),
        'session_checkpoint',
        ['workflow_id'],
        unique=False,
    )

    # Add data_manifest_path to workflow_instance
    with op.batch_alter_table('workflow_instance', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('data_manifest_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove session_checkpoint table."""
    op.drop_index(
        op.f('ix_session_checkpoint_workflow_id'),
        table_name='session_checkpoint',
    )
    op.drop_table('session_checkpoint')

    with op.batch_alter_table('workflow_instance', schema=None) as batch_op:
        batch_op.drop_column('data_manifest_path')

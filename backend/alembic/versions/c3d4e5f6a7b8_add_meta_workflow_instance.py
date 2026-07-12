"""Add meta_workflow_instance table for H2 Meta-Workflow Orchestrator

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add meta_workflow_instance table for DAG-based workflow chaining."""
    with op.batch_alter_table("_dummy_", recreate="never"):
        pass  # batch mode for SQLite

    op.create_table(
        'meta_workflow_instance',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('definition_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''),
        sa.Column('state', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='PENDING'),
        sa.Column('query', sa.Text(), nullable=False, server_default=''),
        sa.Column('budget_total', sa.Float(), nullable=False, server_default='20.0'),
        sa.Column('budget_remaining', sa.Float(), nullable=False, server_default='20.0'),
        sa.Column('node_states', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('node_results', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('spawned_workflows', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('dag_nodes', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('routing_chain', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Remove meta_workflow_instance table."""
    op.drop_table('meta_workflow_instance')

"""Add open_peer_review_entry table for W8 benchmark corpus

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-27 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add open_peer_review_entry table for Phase 6 W8 benchmark corpus."""
    op.create_table(
        'open_peer_review_entry',
        # Primary key: "{source}:{article_id}"
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # Source and identification
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('doi', sa.String(200), nullable=False),
        sa.Column('title', sa.Text(), nullable=False, server_default=''),
        sa.Column('journal', sa.String(100), nullable=False, server_default=''),
        sa.Column('published_year', sa.Integer(), nullable=True),
        # Raw review text
        sa.Column('decision_letter', sa.Text(), nullable=False, server_default=''),
        sa.Column('author_response', sa.Text(), nullable=False, server_default=''),
        sa.Column(
            'editorial_decision',
            sa.String(30),
            nullable=False,
            server_default='',
            comment='accept | major_revision | minor_revision | reject | unknown',
        ),
        # Extracted structured data (JSON blobs)
        sa.Column(
            'parsed_concerns_json',
            sa.Text(),
            nullable=False,
            server_default='[]',
            comment='JSON: list[ReviewerConcern]',
        ),
        # W8 benchmark linkage
        sa.Column('w8_workflow_id', sa.String(36), nullable=True),
        sa.Column(
            'w8_benchmark_json',
            sa.Text(),
            nullable=False,
            server_default='{}',
            comment='JSON: W8BenchmarkResult',
        ),
        # Timestamps
        sa.Column('collected_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_open_peer_review_entry_doi'),
        'open_peer_review_entry',
        ['doi'],
        unique=False,
    )
    op.create_index(
        op.f('ix_open_peer_review_entry_source'),
        'open_peer_review_entry',
        ['source'],
        unique=False,
    )


def downgrade() -> None:
    """Remove open_peer_review_entry table."""
    op.drop_index(
        op.f('ix_open_peer_review_entry_source'),
        table_name='open_peer_review_entry',
    )
    op.drop_index(
        op.f('ix_open_peer_review_entry_doi'),
        table_name='open_peer_review_entry',
    )
    op.drop_table('open_peer_review_entry')

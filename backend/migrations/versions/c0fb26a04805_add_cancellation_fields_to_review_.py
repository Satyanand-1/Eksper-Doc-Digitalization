"""add_cancellation_fields_to_review_workflows

Revision ID: c0fb26a04805
Revises: 9b73ade31935
Create Date: 2026-10-10 14:48:34.699110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c0fb26a04805'
down_revision: Union[str, None] = '9b73ade31935'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add cancellation tracking columns to review_workflows
    op.add_column(
        'review_workflows',
        sa.Column('cancelled_by_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        'review_workflows',
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'review_workflows',
        sa.Column('cancellation_comments', sa.Text(), nullable=True),
    )

    # 2. Add foreign key and index on cancelled_by_id
    op.create_index(
        'ix_review_workflows_cancelled_by_id',
        'review_workflows',
        ['cancelled_by_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_review_workflows_cancelled_by_id_users',
        'review_workflows',
        'users',
        ['cancelled_by_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # Drop foreign key and index, then columns
    op.drop_constraint('fk_review_workflows_cancelled_by_id_users', 'review_workflows', type_='foreignkey')
    op.drop_index('ix_review_workflows_cancelled_by_id', table_name='review_workflows')
    op.drop_column('review_workflows', 'cancellation_comments')
    op.drop_column('review_workflows', 'cancelled_at')
    op.drop_column('review_workflows', 'cancelled_by_id')

"""enforce_single_active_custody_per_file

Revision ID: 851619ad95bc
Revises: 2c7dcaca1ec2
Create Date: 2026-10-11 04:14:41.062327

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '851619ad95bc'
down_revision: Union[str, None] = '2c7dcaca1ec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique index enforcing at database level that no physical file can have more than one ACTIVE custody record
    op.create_index(
        'uq_file_custody_single_active',
        'file_custody_records',
        ['physical_file_id'],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_file_custody_single_active',
        table_name='file_custody_records',
        postgresql_where=sa.text("status = 'active'"),
    )

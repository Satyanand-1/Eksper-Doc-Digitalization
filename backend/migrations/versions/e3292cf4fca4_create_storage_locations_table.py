"""create_storage_locations_table

Revision ID: e3292cf4fca4
Revises: cb9307f34aba
Create Date: 2026-10-11 02:53:33.301037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3292cf4fca4'
down_revision: Union[str, None] = 'cb9307f34aba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create storage_locations table
    op.create_table(
        'storage_locations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('location_code', sa.String(length=64), unique=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('department', sa.String(length=100), nullable=False),
        sa.Column(
            'parent_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('storage_locations.id', ondelete='RESTRICT'),
            nullable=True,
        ),
        sa.Column('max_capacity', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'created_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column(
            'updated_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index('ix_storage_locations_location_code', 'storage_locations', ['location_code'])
    op.create_index('ix_storage_locations_name', 'storage_locations', ['name'])
    op.create_index('ix_storage_locations_location_type', 'storage_locations', ['location_type'])
    op.create_index('ix_storage_locations_department', 'storage_locations', ['department'])
    op.create_index('ix_storage_locations_parent_id', 'storage_locations', ['parent_id'])
    op.create_index('ix_storage_locations_is_active', 'storage_locations', ['is_active'])
    op.create_index('ix_storage_locations_department_status', 'storage_locations', ['department', 'is_active'])

    # 2. Add storage_location_id to physical_files
    op.add_column(
        'physical_files',
        sa.Column(
            'storage_location_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('storage_locations.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.create_index('ix_physical_files_storage_location_id', 'physical_files', ['storage_location_id'])


def downgrade() -> None:
    op.drop_index('ix_physical_files_storage_location_id', table_name='physical_files')
    op.drop_column('physical_files', 'storage_location_id')
    op.drop_index('ix_storage_locations_department_status', table_name='storage_locations')
    op.drop_index('ix_storage_locations_is_active', table_name='storage_locations')
    op.drop_index('ix_storage_locations_parent_id', table_name='storage_locations')
    op.drop_index('ix_storage_locations_department', table_name='storage_locations')
    op.drop_index('ix_storage_locations_location_type', table_name='storage_locations')
    op.drop_index('ix_storage_locations_name', table_name='storage_locations')
    op.drop_index('ix_storage_locations_location_code', table_name='storage_locations')
    op.drop_table('storage_locations')

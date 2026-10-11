"""create_file_custody_and_movement_history_tables

Revision ID: 2c7dcaca1ec2
Revises: e3292cf4fca4
Create Date: 2026-10-11 03:21:04.970822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2c7dcaca1ec2'
down_revision: Union[str, None] = 'e3292cf4fca4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_checked_out column to physical_files table
    op.add_column(
        'physical_files',
        sa.Column('is_checked_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.create_index('ix_physical_files_is_checked_out', 'physical_files', ['is_checked_out'])

    # 2. Create file_custody_records table
    op.create_table(
        'file_custody_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'physical_file_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('physical_files.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'custodian_user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('custodian_name', sa.String(length=255), nullable=False),
        sa.Column('custodian_department', sa.String(length=100), nullable=True),
        sa.Column('custodian_contact', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('checked_out_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('expected_return_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('purpose', sa.Text(), nullable=False),
        sa.Column('checkin_notes', sa.Text(), nullable=True),
        sa.Column(
            'issued_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column(
            'received_by_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index('ix_file_custody_records_physical_file_id', 'file_custody_records', ['physical_file_id'])
    op.create_index('ix_file_custody_records_custodian_user_id', 'file_custody_records', ['custodian_user_id'])
    op.create_index('ix_file_custody_records_status', 'file_custody_records', ['status'])
    op.create_index('ix_file_custody_records_checked_out_at', 'file_custody_records', ['checked_out_at'])
    op.create_index('ix_file_custody_records_expected_return_at', 'file_custody_records', ['expected_return_at'])
    op.create_index('ix_file_custody_records_issued_by_id', 'file_custody_records', ['issued_by_id'])
    op.create_index('ix_file_custody_physical_file_status', 'file_custody_records', ['physical_file_id', 'status'])

    # 3. Create file_movement_history table
    op.create_table(
        'file_movement_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'physical_file_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('physical_files.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('movement_type', sa.String(length=50), nullable=False),
        sa.Column(
            'source_location_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('storage_locations.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'destination_location_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('storage_locations.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('from_custody_state', sa.String(length=255), nullable=True),
        sa.Column('to_custody_state', sa.String(length=255), nullable=True),
        sa.Column(
            'actor_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column('event_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column(
            'custody_record_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('file_custody_records.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index('ix_file_movement_history_physical_file_id', 'file_movement_history', ['physical_file_id'])
    op.create_index('ix_file_movement_history_movement_type', 'file_movement_history', ['movement_type'])
    op.create_index('ix_file_movement_history_actor_id', 'file_movement_history', ['actor_id'])
    op.create_index('ix_file_movement_file_event', 'file_movement_history', ['physical_file_id', 'event_at'])


def downgrade() -> None:
    op.drop_index('ix_file_movement_file_event', table_name='file_movement_history')
    op.drop_index('ix_file_movement_history_actor_id', table_name='file_movement_history')
    op.drop_index('ix_file_movement_history_movement_type', table_name='file_movement_history')
    op.drop_index('ix_file_movement_history_physical_file_id', table_name='file_movement_history')
    op.drop_table('file_movement_history')

    op.drop_index('ix_file_custody_physical_file_status', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_issued_by_id', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_expected_return_at', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_checked_out_at', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_status', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_custodian_user_id', table_name='file_custody_records')
    op.drop_index('ix_file_custody_records_physical_file_id', table_name='file_custody_records')
    op.drop_table('file_custody_records')

    op.drop_index('ix_physical_files_is_checked_out', table_name='physical_files')
    op.drop_column('physical_files', 'is_checked_out')

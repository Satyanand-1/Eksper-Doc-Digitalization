"""create_physical_files_table

Revision ID: cb9307f34aba
Revises: e3f1248ab901
Create Date: 2026-10-11 02:35:30.177264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cb9307f34aba'
down_revision: Union[str, None] = 'e3f1248ab901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create physical_files table
    op.create_table(
        'physical_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('file_reference', sa.String(length=64), unique=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('record_type', sa.String(length=50), nullable=False),
        sa.Column('department', sa.String(length=100), nullable=False),
        sa.Column('classification', sa.String(length=100), nullable=True),
        sa.Column(
            'digital_document_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('digital_documents.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('external_reference', sa.String(length=100), nullable=True),
        sa.Column('date_received', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),
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

    op.create_index('ix_physical_files_file_reference', 'physical_files', ['file_reference'])
    op.create_index('ix_physical_files_title', 'physical_files', ['title'])
    op.create_index('ix_physical_files_record_type', 'physical_files', ['record_type'])
    op.create_index('ix_physical_files_department', 'physical_files', ['department'])
    op.create_index('ix_physical_files_classification', 'physical_files', ['classification'])
    op.create_index('ix_physical_files_digital_document_id', 'physical_files', ['digital_document_id'])
    op.create_index('ix_physical_files_external_reference', 'physical_files', ['external_reference'])
    op.create_index('ix_physical_files_status', 'physical_files', ['status'])
    op.create_index('ix_physical_files_created_by_id', 'physical_files', ['created_by_id'])
    op.create_index('ix_physical_files_department_status', 'physical_files', ['department', 'status'])
    op.create_index('ix_physical_files_created_at', 'physical_files', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_physical_files_created_at', table_name='physical_files')
    op.drop_index('ix_physical_files_department_status', table_name='physical_files')
    op.drop_index('ix_physical_files_created_by_id', table_name='physical_files')
    op.drop_index('ix_physical_files_status', table_name='physical_files')
    op.drop_index('ix_physical_files_external_reference', table_name='physical_files')
    op.drop_index('ix_physical_files_digital_document_id', table_name='physical_files')
    op.drop_index('ix_physical_files_classification', table_name='physical_files')
    op.drop_index('ix_physical_files_department', table_name='physical_files')
    op.drop_index('ix_physical_files_record_type', table_name='physical_files')
    op.drop_index('ix_physical_files_title', table_name='physical_files')
    op.drop_index('ix_physical_files_file_reference', table_name='physical_files')
    op.drop_table('physical_files')

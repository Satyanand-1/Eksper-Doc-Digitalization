"""create_ocr_jobs_table

Revision ID: 26af65844cc3
Revises: d9f158d91b0f
Create Date: 2026-10-10 13:23:59.459271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '26af65844cc3'
down_revision: Union[str, None] = 'd9f158d91b0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ocr_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('worker_id', sa.String(length=100), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_version_id'], ['document_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_version_id', name='uq_ocr_jobs_document_version_id')
    )
    op.create_index('ix_ocr_jobs_document_version_id', 'ocr_jobs', ['document_version_id'], unique=False)
    op.create_index('ix_ocr_jobs_status', 'ocr_jobs', ['status'], unique=False)
    op.create_index('ix_ocr_jobs_next_retry_at', 'ocr_jobs', ['next_retry_at'], unique=False)
    op.create_index('ix_ocr_jobs_lease_expires_at', 'ocr_jobs', ['lease_expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ocr_jobs_lease_expires_at', table_name='ocr_jobs')
    op.drop_index('ix_ocr_jobs_next_retry_at', table_name='ocr_jobs')
    op.drop_index('ix_ocr_jobs_status', table_name='ocr_jobs')
    op.drop_index('ix_ocr_jobs_document_version_id', table_name='ocr_jobs')
    op.drop_table('ocr_jobs')

"""create_retention_and_legal_hold_tables

Revision ID: e3f1248ab901
Revises: ddff27e85a0b
Create Date: 2026-10-11 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3f1248ab901'
down_revision: Union[str, None] = 'ddff27e85a0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create retention_rules table
    op.create_table(
        'retention_rules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), unique=True, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('classification', sa.String(length=100), nullable=True),
        sa.Column('retention_period_unit', sa.String(length=20), nullable=False),
        sa.Column('retention_period_value', sa.Integer(), nullable=False),
        sa.Column('trigger_event', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('updated_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_retention_rules_name', 'retention_rules', ['name'])
    op.create_index('ix_retention_rules_classification', 'retention_rules', ['classification'])
    op.create_index('ix_retention_rules_is_active', 'retention_rules', ['is_active'])

    # 2. Add retention columns to digital_documents
    op.add_column(
        'digital_documents',
        sa.Column('retention_rule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('retention_rules.id', ondelete='SET NULL'), nullable=True)
    )
    op.add_column(
        'digital_documents',
        sa.Column('retention_trigger_date', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'digital_documents',
        sa.Column('retention_start_date', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'digital_documents',
        sa.Column('retention_end_date', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'digital_documents',
        sa.Column('retention_assigned_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'digital_documents',
        sa.Column('retention_assigned_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_digital_documents_retention_rule_id', 'digital_documents', ['retention_rule_id'])
    op.create_index('ix_digital_documents_retention_end_date', 'digital_documents', ['retention_end_date'])

    # 3. Create legal_holds table
    op.create_table(
        'legal_holds',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('digital_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('hold_reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column('placed_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('placed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('released_by_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('release_reason', sa.Text(), nullable=True),
    )
    op.create_index('ix_legal_holds_document_id', 'legal_holds', ['document_id'])
    op.create_index('ix_legal_holds_status', 'legal_holds', ['status'])
    op.create_index('ix_legal_holds_doc_status', 'legal_holds', ['document_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_legal_holds_doc_status', table_name='legal_holds')
    op.drop_index('ix_legal_holds_status', table_name='legal_holds')
    op.drop_index('ix_legal_holds_document_id', table_name='legal_holds')
    op.drop_table('legal_holds')

    op.drop_index('ix_digital_documents_retention_end_date', table_name='digital_documents')
    op.drop_index('ix_digital_documents_retention_rule_id', table_name='digital_documents')
    op.drop_column('digital_documents', 'retention_assigned_by_id')
    op.drop_column('digital_documents', 'retention_assigned_at')
    op.drop_column('digital_documents', 'retention_end_date')
    op.drop_column('digital_documents', 'retention_start_date')
    op.drop_column('digital_documents', 'retention_trigger_date')
    op.drop_column('digital_documents', 'retention_rule_id')

    op.drop_index('ix_retention_rules_is_active', table_name='retention_rules')
    op.drop_index('ix_retention_rules_classification', table_name='retention_rules')
    op.drop_index('ix_retention_rules_name', table_name='retention_rules')
    op.drop_table('retention_rules')

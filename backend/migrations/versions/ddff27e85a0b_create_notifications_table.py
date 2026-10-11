"""create_notifications_table

Revision ID: ddff27e85a0b
Revises: c0fb26a04805
Create Date: 2026-10-10 15:01:41.162242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ddff27e85a0b'
down_revision: Union[str, None] = 'c0fb26a04805'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('recipient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('digital_documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('review_workflows.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_notifications_recipient_id', 'notifications', ['recipient_id'])
    op.create_index('ix_notifications_notification_type', 'notifications', ['notification_type'])
    op.create_index('ix_notifications_document_id', 'notifications', ['document_id'])
    op.create_index('ix_notifications_workflow_id', 'notifications', ['workflow_id'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    op.create_index('ix_notifications_recipient_created', 'notifications', ['recipient_id', 'created_at'])
    op.create_index('ix_notifications_recipient_unread', 'notifications', ['recipient_id', 'is_read'])


def downgrade() -> None:
    op.drop_index('ix_notifications_recipient_unread', table_name='notifications')
    op.drop_index('ix_notifications_recipient_created', table_name='notifications')
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_is_read', table_name='notifications')
    op.drop_index('ix_notifications_workflow_id', table_name='notifications')
    op.drop_index('ix_notifications_document_id', table_name='notifications')
    op.drop_index('ix_notifications_notification_type', table_name='notifications')
    op.drop_index('ix_notifications_recipient_id', table_name='notifications')
    op.drop_table('notifications')

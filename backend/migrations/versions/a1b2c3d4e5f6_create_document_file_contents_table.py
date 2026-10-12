"""create_document_file_contents_table

Revision ID: a1b2c3d4e5f6
Revises: 851619ad95bc
Create Date: 2026-10-12 10:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '851619ad95bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use if_not_exists check
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if 'document_file_contents' not in tables:
        op.create_table(
            'document_file_contents',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                'version_id',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('document_versions.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('file_bytes', sa.LargeBinary(), nullable=False),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
        )
        op.create_index(
            'ix_document_file_contents_version_id',
            'document_file_contents',
            ['version_id'],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index('ix_document_file_contents_version_id', table_name='document_file_contents')
    op.drop_table('document_file_contents')

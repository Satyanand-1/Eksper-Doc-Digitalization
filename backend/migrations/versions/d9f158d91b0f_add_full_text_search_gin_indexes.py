"""add_full_text_search_gin_indexes

Revision ID: d9f158d91b0f
Revises: f00bd930ec9e
Create Date: 2026-10-10 13:06:13.144448

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f158d91b0f'
down_revision: Union[str, None] = 'f00bd930ec9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. GIN expression index on digital_documents metadata (title, document_reference, subject)
    # Includes reference both raw and space-delimited to support searching whole code or parts
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_digital_documents_fts
        ON digital_documents
        USING gin(
            (
                setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('english', coalesce(document_reference, '') || ' ' || replace(coalesce(document_reference, ''), '-', ' ')), 'A') ||
                setweight(to_tsvector('english', coalesce(subject, '')), 'B')
            )
        );
        """
    )

    # 2. GIN expression index on document_versions extracted_text
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_versions_extracted_text_fts
        ON document_versions
        USING gin(
            (to_tsvector('english', coalesce(extracted_text, '')))
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_versions_extracted_text_fts;")
    op.execute("DROP INDEX IF EXISTS ix_digital_documents_fts;")

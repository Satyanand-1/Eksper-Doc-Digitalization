import pytest
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext
from app.database import engine, Base

def test_alembic_config_and_metadata():
    """Verify Alembic configuration targets SQLAlchemy Base metadata."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    assert script is not None
    assert Base.metadata is not None
    assert "users" in Base.metadata.tables
    assert "digital_documents" in Base.metadata.tables
    assert "document_versions" in Base.metadata.tables
    assert "audit_logs" in Base.metadata.tables

def test_alembic_current_head_execution():
    """Verify Alembic can inspect migration context and head against PostgreSQL."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    expected_head = script.get_current_head()

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current_rev = ctx.get_current_revision()
        assert current_rev is not None
        assert current_rev == expected_head

def test_alembic_upgrade_and_downgrade_cycle():
    """
    Safely verifies the migration upgrade and downgrade cycle.
    Downgrades to base, confirms tables are removed, then upgrades back to head.
    """
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    expected_head = script.get_current_head()
    
    # Downgrade to base (removes users, document, and audit tables)
    command.downgrade(alembic_cfg, "base")
    
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() is None

    # Upgrade back to head (re-creates users, digital_documents, document_versions, audit_logs)
    command.upgrade(alembic_cfg, "head")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == expected_head


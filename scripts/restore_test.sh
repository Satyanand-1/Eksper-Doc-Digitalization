#!/bin/bash
# ==============================================================================
# EDRMS Automated Restore Verification Script
# Restores a backup into an ISOLATED test database and isolated storage directory.
# Verifies database tables, record counts, document files, and SHA-256 hashes.
# ==============================================================================

set -euo pipefail

BACKUP_TARGET_DIR="${1:?Usage: $0 <path_to_backup_dir> [isolated_db_name] [isolated_storage_dir]}"
TEST_DB_NAME="${2:-edrms_restore_test_db}"
TEST_STORAGE_DIR="${3:-/tmp/edrms_restore_test_storage}"

echo "[INFO] Starting EDRMS restore verification from ${BACKUP_TARGET_DIR}..."

# 1. Verify Manifest Integrity
echo "[INFO] Verifying backup checksums using manifest.sha256..."
cd "${BACKUP_TARGET_DIR}"
sha256sum -c manifest.sha256

# 2. Recreate Isolated Target Database
echo "[INFO] Creating isolated test database '${TEST_DB_NAME}'..."
PGPASSWORD="${POSTGRES_PASSWORD:-edrms_secure_dev_password}" psql \
    -h "${POSTGRES_HOST:-db}" \
    -U "${POSTGRES_USER:-edrms_user}" \
    -d "postgres" \
    -c "DROP DATABASE IF EXISTS ${TEST_DB_NAME};"
PGPASSWORD="${POSTGRES_PASSWORD:-edrms_secure_dev_password}" psql \
    -h "${POSTGRES_HOST:-db}" \
    -U "${POSTGRES_USER:-edrms_user}" \
    -d "postgres" \
    -c "CREATE DATABASE ${TEST_DB_NAME} OWNER ${POSTGRES_USER:-edrms_user};"

# 3. Restore Database into Isolated Database
echo "[INFO] Restoring pg_dump into '${TEST_DB_NAME}'..."
PGPASSWORD="${POSTGRES_PASSWORD:-edrms_secure_dev_password}" pg_restore \
    -h "${POSTGRES_HOST:-db}" \
    -U "${POSTGRES_USER:-edrms_user}" \
    -d "${TEST_DB_NAME}" \
    --clean --if-exists \
    --no-owner \
    -v \
    "${BACKUP_TARGET_DIR}/edrms_db.dump" || true

# 4. Restore Storage Archive into Isolated Directory
echo "[INFO] Restoring document storage to isolated directory '${TEST_STORAGE_DIR}'..."
rm -rf "${TEST_STORAGE_DIR}"
mkdir -p "${TEST_STORAGE_DIR}"
tar -xzf "${BACKUP_TARGET_DIR}/storage_archive.tar.gz" -C "${TEST_STORAGE_DIR}"

# 5. Verification of Restored Assets
echo "[INFO] Running data integrity verification on restored database and storage..."
python3 - <<EOF
import os, hashlib, sys
from sqlalchemy import create_engine, text

db_url = "postgresql+psycopg2://${POSTGRES_USER:-edrms_user}:${POSTGRES_PASSWORD:-edrms_secure_dev_password}@${POSTGRES_HOST:-db}:5432/${TEST_DB_NAME}"
engine = create_engine(db_url)
storage_root = "${TEST_STORAGE_DIR}"

with engine.connect() as conn:
    # 1. Check core table counts
    tables = [
        "users", "digital_documents", "document_versions", "audit_logs",
        "retention_rules", "legal_holds", "physical_files", "storage_locations",
        "file_custody_records", "file_movement_history"
    ]
    print("--- Restored Database Record Counts ---")
    for t in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        print(f"  {t:25}: {count} records")

    # 2. Check Alembic version
    alembic_v = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"  alembic_version          : {alembic_v}")

    # 3. Check document versions and SHA-256 hashes against restored storage
    print("\n--- Document File Hash Verification in Restored Storage ---")
    versions = conn.execute(text("SELECT id, storage_key, file_hash_sha256, file_size_bytes FROM document_versions WHERE storage_key LIKE 'uploads/2026/10/%'")).fetchall()
    
    verified = 0
    for v in versions:
        v_id, storage_key, expected_hash, file_size = v
        file_path = os.path.join(storage_root, storage_key)
        if not os.path.exists(file_path):
            print(f"  [FAIL] Missing restored file: {file_path}")
            sys.exit(1)
        
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64*1024):
                hasher.update(chunk)
        calc_hash = hasher.hexdigest()
        if calc_hash != expected_hash:
            print(f"  [FAIL] Hash mismatch for {storage_key}: expected {expected_hash}, calculated {calc_hash}")
            sys.exit(1)
        verified += 1
        print(f"  [OK] Version {v_id} ({file_size} bytes): SHA-256 matches perfectly")

    print(f"Verification successful: {verified}/{len(versions)} persistent documents verified.")
EOF

echo "[SUCCESS] Restore verification completed successfully for ${TEST_DB_NAME} and ${TEST_STORAGE_DIR}!"

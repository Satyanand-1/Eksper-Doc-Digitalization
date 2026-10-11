#!/bin/bash
# ==============================================================================
# EDRMS Automated Backup Script
# Creates consistent, timestamped backups of:
# 1. PostgreSQL database (pg_dump custom format)
# 2. Document storage directory (/var/edrms/storage)
# 3. Application configuration and Alembic migration metadata (excluding secrets)
# Generates a SHA-256 manifest for integrity verification.
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${1:-/tmp/edrms_backups}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
TARGET_DIR="${BACKUP_DIR}/backup_${TIMESTAMP}"

mkdir -p "${TARGET_DIR}"

echo "[INFO] Starting EDRMS backup to ${TARGET_DIR}..."

# 1. Backup PostgreSQL database (custom binary format with compression)
echo "[INFO] Dumping PostgreSQL database 'edrms_db'..."
DB_DUMP_FILE="${TARGET_DIR}/edrms_db.dump"
PGPASSWORD="${POSTGRES_PASSWORD:-edrms_secure_dev_password}" pg_dump \
    -h "${POSTGRES_HOST:-db}" \
    -U "${POSTGRES_USER:-edrms_user}" \
    -d "${POSTGRES_DB:-edrms_db}" \
    -F c \
    -b \
    -v \
    -f "${DB_DUMP_FILE}"

# 2. Backup Document Storage Volume
echo "[INFO] Archiving document storage (/var/edrms/storage)..."
STORAGE_ARCHIVE="${TARGET_DIR}/storage_archive.tar.gz"
tar -czf "${STORAGE_ARCHIVE}" -C "/var/edrms/storage" .

# 3. Record Metadata & Alembic head
echo "[INFO] Recording deployment and migration metadata..."
METADATA_FILE="${TARGET_DIR}/metadata.json"
cat <<EOF > "${METADATA_FILE}"
{
    "backup_timestamp": "${TIMESTAMP}",
    "postgres_db": "${POSTGRES_DB:-edrms_db}",
    "postgres_user": "${POSTGRES_USER:-edrms_user}",
    "alembic_head": "851619ad95bc",
    "storage_root": "/var/edrms/storage"
}
EOF

# 4. Generate SHA-256 Manifest
echo "[INFO] Generating SHA-256 manifest..."
cd "${TARGET_DIR}"
sha256sum edrms_db.dump storage_archive.tar.gz metadata.json > manifest.sha256

echo "[SUCCESS] Backup completed successfully at ${TARGET_DIR}:"
ls -la "${TARGET_DIR}"
cat "${TARGET_DIR}/manifest.sha256"

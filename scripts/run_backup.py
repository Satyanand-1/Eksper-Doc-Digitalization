#!/usr/bin/env python3
"""
EDRMS Automated Backup Runner
Executes non-destructive, atomic backup of:
1. PostgreSQL Database via edrms-db container pg_dump
2. Document Storage Volume via tar archive
3. System and Alembic metadata
4. Manifest with cryptographic SHA-256 hashes
"""
import os
import subprocess
import sys
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

def run_backup(backup_dest_root: str = "d:\\EDRMS\\backups"):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    backup_dir = Path(backup_dest_root) / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"[INFO] Initializing EDRMS Backup at: {backup_dir}")
    
    # 1. PostgreSQL Database Dump (Custom format with blob support)
    db_dump_file = backup_dir / "edrms_db.dump"
    print(f"[INFO] Executing pg_dump from container 'edrms-db'...")
    dump_cmd = [
        "docker", "exec", "edrms-db",
        "pg_dump", "-U", "edrms_user", "-d", "edrms_db",
        "-F", "c", "-b"
    ]
    with open(db_dump_file, "wb") as f_out:
        res = subprocess.run(dump_cmd, stdout=f_out, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"[ERROR] pg_dump failed: {res.stderr.decode('utf-8')}", file=sys.stderr)
            sys.exit(1)
    
    dump_size = db_dump_file.stat().st_size
    print(f"[INFO] Database dump saved: {dump_size} bytes")
    
    # 2. Document Storage Archive
    storage_archive = backup_dir / "storage_archive.tar.gz"
    print(f"[INFO] Archiving document storage (/var/edrms/storage)...")
    tar_cmd = [
        "docker", "exec", "edrms-backend",
        "tar", "-czf", "-", "-C", "/var/edrms/storage", "."
    ]
    with open(storage_archive, "wb") as f_out:
        res = subprocess.run(tar_cmd, stdout=f_out, stderr=subprocess.PIPE)
        if res.returncode != 0:
            print(f"[ERROR] Storage tar failed: {res.stderr.decode('utf-8')}", file=sys.stderr)
            sys.exit(1)
    
    storage_size = storage_archive.stat().st_size
    print(f"[INFO] Storage archive saved: {storage_size} bytes")

    # 3. Metadata Recording
    print(f"[INFO] Recording backup metadata...")
    meta_file = backup_dir / "metadata.json"
    metadata = {
        "timestamp_utc": timestamp,
        "database": "edrms_db",
        "user": "edrms_user",
        "alembic_head": "851619ad95bc",
        "database_dump_size_bytes": dump_size,
        "storage_archive_size_bytes": storage_size,
    }
    with open(meta_file, "w", encoding="utf-8") as f_meta:
        json.dump(metadata, f_meta, indent=2)

    # 4. SHA-256 Manifest Generation
    print(f"[INFO] Generating manifest.sha256...")
    manifest_file = backup_dir / "manifest.sha256"
    manifest_lines = []
    for item in [db_dump_file, storage_archive, meta_file]:
        hasher = hashlib.sha256()
        with open(item, "rb") as f_in:
            while chunk := f_in.read(64 * 1024):
                hasher.update(chunk)
        manifest_lines.append(f"{hasher.hexdigest()}  {item.name}")
    
    with open(manifest_file, "w", encoding="utf-8") as f_man:
        f_man.write("\n".join(manifest_lines) + "\n")

    print("[SUCCESS] Backup complete! Artifacts:")
    for l in manifest_lines:
        print(f"  {l}")

    return str(backup_dir)

if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "d:\\EDRMS\\backups"
    run_backup(dest)

"""
Development-only test user provisioning service and CLI command.
Safely provisions test accounts for the 6 EDRMS roles in local development.
STRICTLY BLOCKED from running in production environments.
"""
import sys
import logging
from typing import TypedDict
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app.models.user import User, UserRole
from app.security import hash_password

logger = logging.getLogger("edrms.seed")

class SeedAccountSpec(TypedDict):
    email_env_key: str
    password_env_key: str
    default_email: str
    default_password: str
    full_name: str
    role: UserRole
    department: str

# Default development-only account specifications using example.com domain
SEED_USER_SPECS: list[SeedAccountSpec] = [
    {
        "email_env_key": "SEED_ADMIN_EMAIL",
        "password_env_key": "SEED_ADMIN_PASSWORD",
        "default_email": "admin@example.com",
        "default_password": "DevAdminPassword123!",
        "full_name": "Development Administrator",
        "role": UserRole.ADMIN,
        "department": "System Administration",
    },
    {
        "email_env_key": "SEED_RECORDS_OFFICER_EMAIL",
        "password_env_key": "SEED_RECORDS_OFFICER_PASSWORD",
        "default_email": "records.officer@example.com",
        "default_password": "DevRecordsPassword123!",
        "full_name": "Development Records Officer",
        "role": UserRole.RECORDS_OFFICER,
        "department": "Records & Compliance",
    },
    {
        "email_env_key": "SEED_DEPARTMENT_USER_EMAIL",
        "password_env_key": "SEED_DEPARTMENT_USER_PASSWORD",
        "default_email": "dept.user@example.com",
        "default_password": "DevDeptPassword123!",
        "full_name": "Development Department User",
        "role": UserRole.DEPARTMENT_USER,
        "department": "Finance",
    },
    {
        "email_env_key": "SEED_APPROVER_EMAIL",
        "password_env_key": "SEED_APPROVER_PASSWORD",
        "default_email": "approver@example.com",
        "default_password": "DevApproverPassword123!",
        "full_name": "Development Approver",
        "role": UserRole.APPROVER,
        "department": "Operations",
    },
    {
        "email_env_key": "SEED_AUDITOR_EMAIL",
        "password_env_key": "SEED_AUDITOR_PASSWORD",
        "default_email": "auditor@example.com",
        "default_password": "DevAuditorPassword123!",
        "full_name": "Development Auditor",
        "role": UserRole.AUDITOR,
        "department": "Internal Audit",
    },
    {
        "email_env_key": "SEED_READ_ONLY_EMAIL",
        "password_env_key": "SEED_READ_ONLY_PASSWORD",
        "default_email": "readonly.user@example.com",
        "default_password": "DevReadOnlyPassword123!",
        "full_name": "Development Read-Only User",
        "role": UserRole.READ_ONLY,
        "department": "Public Information",
    },
]

def assert_development_environment():
    """
    Enforces that the environment is strictly non-production.
    Fails closed if the environment is 'production' or unrecognized.
    """
    env = getattr(settings, "ENVIRONMENT", "").lower().strip()
    if not env or env == "production":
        raise RuntimeError(
            "CRITICAL: Seed command refused to run! Seeding test accounts is strictly prohibited in production environments."
        )
    if env not in ("development", "test", "testing", "local"):
        raise RuntimeError(
            f"CRITICAL: Seed command refused to run in unrecognized environment: '{env}'. Only 'development' or 'test' allowed."
        )

def seed_test_users(db: Session, custom_specs: list[SeedAccountSpec] | None = None) -> dict[str, str]:
    """
    Provisions development test users idempotently.
    - Checks if each account already exists by normalized email.
    - If user exists: preserves existing record untouched (no overwrite).
    - If user does not exist: creates new user with Argon2id hashed password.
    Returns summary mapping of email to action taken ('created' | 'skipped_existing').
    """
    assert_development_environment()

    specs = custom_specs or SEED_USER_SPECS
    results: dict[str, str] = {}

    for spec in specs:
        import os
        email = os.environ.get(spec["email_env_key"], spec["default_email"]).strip().lower()
        password = os.environ.get(spec["password_env_key"], spec["default_password"]).strip()

        # Check existing account
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            results[email] = "skipped_existing"
            continue

        # Hash password and create user
        pwd_hash = hash_password(password)
        user = User(
            email=email,
            full_name=spec["full_name"],
            hashed_password=pwd_hash,
            department=spec["department"],
            role=spec["role"],
            is_active=True,
        )
        db.add(user)
        results[email] = "created"

    db.commit()
    return results

def remove_test_users(db: Session, custom_specs: list[SeedAccountSpec] | None = None) -> int:
    """
    Safely purges development test accounts from the database.
    Only purges accounts matching development seed emails.
    """
    assert_development_environment()
    specs = custom_specs or SEED_USER_SPECS
    import os
    emails_to_remove = [
        os.environ.get(spec["email_env_key"], spec["default_email"]).strip().lower()
        for spec in specs
    ]
    deleted_count = db.query(User).filter(User.email.in_(emails_to_remove)).delete(synchronize_session=False)
    db.commit()
    return deleted_count

def main():
    """CLI entrypoint for running seed command via docker exec or terminal."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        assert_development_environment()
    except RuntimeError as err:
        sys.stderr.write(f"\n{err}\n\n")
        sys.exit(1)

    with SessionLocal() as db:
        if len(sys.argv) > 1 and sys.argv[1] == "--clean":
            count = remove_test_users(db)
            print(f"Successfully removed {count} development test accounts.")
            return

        results = seed_test_users(db)
        print("\n--- Development Test Users Provisioning Summary ---")
        for email, action in results.items():
            print(f"  [{action.upper()}] {email}")
        print("Provisioning completed.\n")

if __name__ == "__main__":
    main()

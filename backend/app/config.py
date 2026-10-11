import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    DATABASE_URL: str = "postgresql+psycopg2://edrms_user:edrms_secure_dev_password@db:5432/edrms_db"
    STORAGE_ROOT: str = "/var/edrms/storage"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True

    # Upload constraints (default: 25 MiB)
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

    # JWT Authentication Settings
    JWT_SECRET_KEY: str = "dev_insecure_jwt_secret_key_change_in_production_min_32_bytes_len"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # OCR and Text Extraction Limits
    OCR_MAX_PAGES: int = 50
    OCR_TIMEOUT_SECONDS: int = 30
    OCR_MAX_FILE_SIZE_BYTES: int = 25 * 1024 * 1024
    TESSERACT_CMD: str = "tesseract"

    # Durable OCR Worker Settings
    OCR_WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    OCR_WORKER_LEASE_SECONDS: int = 60
    OCR_WORKER_MAX_ATTEMPTS: int = 3
    OCR_WORKER_BASE_RETRY_DELAY_SECONDS: int = 5
    OCR_WORKER_BATCH_SIZE: int = 5

    # CORS Settings
    ALLOWED_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Fail fast if insecure defaults or weak keys are used in production."""
        if self.ENVIRONMENT.lower() == "production":
            if "dev_insecure" in self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("In production, JWT_SECRET_KEY must be a strong secret of at least 32 characters.")
            if self.ALLOWED_ORIGINS == "*":
                raise ValueError("In production, ALLOWED_ORIGINS must not be '*' (wildcard). Set explicit trusted domains.")
        return self

settings = Settings()

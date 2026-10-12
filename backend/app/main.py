import logging
from fastapi import FastAPI, Depends, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router
from app.api.v1.ocr import router as ocr_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.users import router as users_router
from app.api.v1.audit_logs import router as audit_logs_router
from app.api.v1.retention import router as retention_router
from app.api.v1.physical_files import router as physical_files_router
from app.api.v1.storage_locations import router as storage_locations_router

from contextlib import asynccontextmanager

logger = logging.getLogger("edrms")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all models and tables exist on startup (including document_file_contents)
    try:
        from app.database import engine, Base
        import app.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning(f"Metadata create_all notice: {exc}")
    yield

app = FastAPI(
    title="EDRMS Backend API",
    description="Electronic Document and Records Management System API",
    version="0.1.0",
    lifespan=lifespan,
)

# Parse allowed origins from configuration
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
if not origins:
    origins = ["*"]

# In development or when wildcard is permitted, credentials cannot be used with '*' per CORS spec
allow_creds = origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_creds,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if "X-Frame-Options" not in response.headers:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Register API routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(ocr_router)
app.include_router(workflows_router)
app.include_router(notifications_router)
app.include_router(users_router)
app.include_router(audit_logs_router)
app.include_router(retention_router)
app.include_router(physical_files_router)
app.include_router(storage_locations_router)

@app.get("/", tags=["Root"])
def root_status():
    return {
        "status": "online",
        "service": "EDRMS Backend API",
        "version": "0.1.0",
        "docs_url": "/docs",
        "health_check": "/api/v1/health",
    }

@app.get("/api/v1/health", tags=["Health"])
def liveness_check():
    """
    Application liveness probe.
    Quickly verifies that the web service is running and accepting requests.
    """
    return {
        "status": "healthy",
        "service": "edrms-backend",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
    }

@app.get("/api/v1/health/ready", tags=["Health"])
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """
    Application readiness probe with database connectivity check.
    Confirms the application is ready to process traffic and can reach PostgreSQL.
    Credentials and raw error traces are never exposed.
    """
    try:
        # Execute lightweight database query
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "service": "edrms-backend",
            "database": {
                "status": "connected",
            },
        }
    except Exception as exc:
        logger.error(f"Readiness check failed: {exc}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unavailable",
            "service": "edrms-backend",
            "database": {
                "status": "disconnected",
            },
        }

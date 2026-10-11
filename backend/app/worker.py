"""
CLI runner for the dedicated background OCR worker process.
Handles graceful shutdown (SIGINT/SIGTERM), database readiness checks,
and resilient polling.
"""
import logging
import signal
import sys
import threading
import time
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.services.ocr_worker import ocr_job_service

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)

logger = logging.getLogger("edrms.worker_main")

stop_event = threading.Event()


def handle_signal(sig, frame):
    logger.info(f"Received exit signal {sig}, triggering graceful shutdown...")
    stop_event.set()


def wait_for_database(max_wait_seconds: int = 60) -> bool:
    """Blocks until PostgreSQL database is accessible and responsive."""
    logger.info("Waiting for database connectivity...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        if stop_event.is_set():
            return False
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("Database connection established successfully.")
                return True
        except Exception as e:
            logger.warning(f"Database unavailable ({e}); retrying in 2 seconds...")
            time.sleep(2)
    logger.error("Timed out waiting for database readiness.")
    return False


def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logger.info(f"Initializing EDRMS OCR Worker Service (worker ID: {ocr_job_service.worker_id})...")

    if not wait_for_database():
        logger.critical("Failed to connect to database. Exiting worker process.")
        sys.exit(1)

    try:
        ocr_job_service.run_worker_loop(stop_event=stop_event)
    except Exception as exc:
        logger.critical(f"Fatal error in worker execution: {exc}", exc_info=True)
        sys.exit(1)

    logger.info("OCR worker process terminated cleanly.")


if __name__ == "__main__":
    main()

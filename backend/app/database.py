"""
Database engine / session setup for UrbanDash complaint triage backend.
Uses PostgreSQL (see README for rationale).
"""
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@db:5432/urbandash",
)

# Retry connecting a few times since the db container may still be starting
# when the backend container boots (docker-compose has no built-in wait).
_engine = None
_last_error = None
for attempt in range(30):
    try:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        conn = _engine.connect()
        conn.close()
        break
    except Exception as exc:  # noqa: BLE001
        _last_error = exc
        _engine = None
        time.sleep(2)

if _engine is None:
    raise RuntimeError(
        f"Could not connect to database after retries: {_last_error}"
    )

engine = _engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

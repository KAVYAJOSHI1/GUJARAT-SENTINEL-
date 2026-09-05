"""
SQLAlchemy engine + session management.
Uses a connection pool sized per config; exposes a FastAPI dependency
`get_db` that yields a scoped session and always closes it.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError

from app.config import settings


def _connect_args() -> dict:
    """psycopg2 connect args. `options` sets a server-side statement_timeout
    for every session on this pool -- a runaway query is cancelled rather
    than pinning a connection. `application_name` makes the backend easy to
    spot in pg_stat_activity."""
    args: dict = {"application_name": "sentinel-backend"}
    if settings.DB_STATEMENT_TIMEOUT_MS and settings.DB_STATEMENT_TIMEOUT_MS > 0:
        args["options"] = f"-c statement_timeout={int(settings.DB_STATEMENT_TIMEOUT_MS)}"
    return args


engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS or -1,
    pool_pre_ping=True,
    connect_args=_connect_args(),
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, future=True
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a DB session; rolls back + closes on exit."""
    db = SessionLocal()
    try:
        yield db
    except OperationalError:
        db.rollback()
        raise
    finally:
        db.close()

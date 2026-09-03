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

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
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

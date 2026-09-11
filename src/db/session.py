"""
Database session management for FEMA CRIA.

Provides session factory and context managers for database operations.
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from src.config.settings import settings
from src.utils.logger import logger


# Create engine based on database URL
def create_db_engine():
    """
    Create SQLAlchemy engine based on database URL from settings.

    Returns:
        SQLAlchemy engine instance
    """
    db_url = settings.database_url

    # Special handling for SQLite (for testing)
    if db_url.startswith("sqlite"):
        logger.info(f"Creating SQLite engine: {db_url}")
        engine = create_engine(
            db_url,
            echo=settings.debug,
            connect_args={"check_same_thread": False},  # Allow multi-threading
            poolclass=StaticPool,  # Use static pool for SQLite
        )

        # Enable foreign keys for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    else:
        # PostgreSQL configuration
        logger.info(f"Creating PostgreSQL engine: {db_url.split('@')[1] if '@' in db_url else db_url}")
        engine = create_engine(
            db_url,
            echo=settings.debug,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,
            max_overflow=10,
        )

    return engine


# Create engine and session factory
engine = create_db_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic commit/rollback.

    Yields:
        SQLAlchemy Session instance

    Example:
        >>> with get_db() as db:
        ...     geography = Geography(geo_id="GEO_001", name="Test County")
        ...     db.add(geography)
        ...     # Automatically commits on exit
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error, rolling back: {e}")
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Get a database session (for dependency injection).

    Returns:
        SQLAlchemy Session instance

    Note:
        Caller is responsible for closing the session.

    Example:
        >>> db = get_db_session()
        >>> try:
        ...     geography = Geography(geo_id="GEO_001", name="Test County")
        ...     db.add(geography)
        ...     db.commit()
        ... finally:
        ...     db.close()
    """
    return SessionLocal()


def init_db():
    """
    Initialize database (create all tables).

    This should only be called during initial setup or testing.
    For production, use Alembic migrations.

    Example:
        >>> from src.db.models import Base
        >>> from src.db.session import init_db
        >>> init_db()  # Creates all tables
    """
    from src.db.models import Base

    logger.info("Initializing database (creating tables)")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")


def drop_db():
    """
    Drop all database tables.

    WARNING: This will delete all data!
    Only use for testing or development.

    Example:
        >>> from src.db.session import drop_db
        >>> drop_db()  # Drops all tables
    """
    from src.db.models import Base

    logger.warning("Dropping all database tables")
    Base.metadata.drop_all(bind=engine)
    logger.info("Database tables dropped")


def reset_db():
    """
    Reset database (drop and recreate all tables).

    WARNING: This will delete all data!
    Only use for testing or development.

    Example:
        >>> from src.db.session import reset_db
        >>> reset_db()  # Drops and recreates all tables
    """
    logger.warning("Resetting database")
    drop_db()
    init_db()
    logger.info("Database reset complete")

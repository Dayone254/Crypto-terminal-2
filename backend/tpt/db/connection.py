"""SQLAlchemy async engine and session factory."""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tpt.config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={
        "check_same_thread": False,
        # Let SQLite itself wait for a contended write lock instead of failing
        # instantly. Must be >= the longest write transaction in the app.
        "timeout": 30.0,
    },
)

# Keep in sync with data/database.py — one starvation budget for every writer.
BUSY_TIMEOUT_MS = 30_000


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    cursor.close()


AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    """FastAPI dependency for DB sessions."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Unified, idempotent database initializer creating all ORM models and raw signals tables."""
    from tpt.data.database import init_db as init_raw_signals_db
    from tpt.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await init_raw_signals_db()

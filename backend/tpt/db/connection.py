"""SQLAlchemy async engine and session factory."""
from __future__ import annotations

from collections.abc import AsyncGenerator

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
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    cursor.close()


AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Unified, idempotent database initializer creating all ORM models and raw signals tables."""
    from sqlalchemy import text

    from tpt.data.database import init_db as init_raw_signals_db
    from tpt.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lookup indexes: per-symbol score lookups for /markets/{id}/ladder
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scores_product_scan ON scores(product_id, scan_run_id DESC);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ladders_product_scan ON ladders(product_id, scan_run_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_features_product_scan ON features(product_id, scan_run_id);"))
        # Market list indexes: scan_run_id join and composite score ordering for /markets
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scores_scan_run ON scores(scan_run_id);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scores_composite ON scores(scan_run_id, composite_score DESC);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scan_runs_status_time ON scan_runs(status, started_at DESC);"))
        # Covering indexes for trade history route: per-symbol ordered by computed_at.
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scores_pid_time ON scores(product_id, computed_at ASC);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ladders_pid_time ON ladders(product_id, computed_at ASC);"))

    await init_raw_signals_db()


"""Shared pytest fixtures.

Critical: point the whole application at a throwaway database BEFORE anything
imports `tpt`. Previously there was no conftest at all, so the test suite ran
against the live `backend/tpt/data/backtest.db` — pinning/unpinning real
watchlist symbols and contending with the running server for the write lock.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="tpt_test_"))
_DB_FILE = _TMP_DIR / "test.db"

# Must be set before `tpt.config.settings` is imported anywhere.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}"
os.environ.setdefault("SCAN_INTERVAL_SECONDS", "0")  # never auto-scan during tests
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENABLE_ML_SCORING", "false")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def test_db_path() -> Path:
    return _DB_FILE


@pytest.fixture(scope="session", autouse=True)
def _isolated_db():
    """Guard rail: fail loudly if anything escapes to the real database."""
    from tpt.config.settings import settings

    assert settings.sqlite_path == _DB_FILE.as_posix(), (
        f"Tests must run against the temp DB, got {settings.sqlite_path}"
    )
    yield
    shutil.rmtree(_TMP_DIR, ignore_errors=True)

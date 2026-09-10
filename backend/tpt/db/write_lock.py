"""Process-wide SQLite write serialization.

SQLite (even in WAL mode) permits exactly **one writer at a time**. Concurrent
writers — the scanner, the backtest evaluator daemon, and API request handlers —
all share the same database file, so any two overlapping write transactions
produce `sqlite3.OperationalError: database is locked`.

`ARCHITECTURE.md` §5.3 specifies that all writes route through a single
`asyncio.Lock`. This module is that lock. Import it and wrap write transactions:

    async with db_write_lock:
        ...  # open session / connection, mutate, commit

Keep the critical section free of network I/O where possible; the lock is held
for the whole transaction, so anything slow inside it stalls other writers.
"""
from __future__ import annotations

import asyncio

db_write_lock = asyncio.Lock()

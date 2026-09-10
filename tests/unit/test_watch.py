"""Unit tests for watchlist database queries and active watch functions."""
import pytest

from tpt.db.connection import AsyncSessionLocal, init_db
from tpt.db.queries import add_to_watchlist, get_watchlist, remove_from_watchlist


@pytest.mark.asyncio
async def test_watchlist_crud() -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        # Add symbol
        sym = await add_to_watchlist(db, "ZORA-USD")
        assert sym.product_id == "ZORA-USD"
        assert sym.on_watchlist == 1

        # List watchlist
        items = await get_watchlist(db)
        assert any(i.product_id == "ZORA-USD" for i in items)

        # Remove symbol
        ok = await remove_from_watchlist(db, "ZORA-USD")
        assert ok is True

        # Verify removal
        items_after = await get_watchlist(db)
        assert not any(i.product_id == "ZORA-USD" for i in items_after)

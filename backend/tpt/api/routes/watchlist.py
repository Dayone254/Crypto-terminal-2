"""Watchlist API routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from tpt.db.connection import AsyncSessionLocal
from tpt.db.queries import add_to_watchlist, get_watchlist, remove_from_watchlist

router = APIRouter()


@router.get("", response_model=list[dict[str, Any]])
async def list_watchlist_items() -> list[dict[str, Any]]:
    """Return all pinned watchlist symbols."""
    async with AsyncSessionLocal() as db:
        symbols = await get_watchlist(db)
        return [
            {
                "product_id": s.product_id,
                "base_currency": s.base_currency,
                "quote_currency": s.quote_currency,
                "display_name": s.display_name,
                "on_watchlist": s.on_watchlist,
                "active": s.active,
            }
            for s in symbols
        ]


@router.post("/{product_id}", response_model=dict[str, Any])
async def pin_symbol(product_id: str) -> dict[str, Any]:
    """Pin a symbol to the watchlist."""
    async with AsyncSessionLocal() as db:
        sym = await add_to_watchlist(db, product_id.upper())
        return {
            "product_id": sym.product_id,
            "on_watchlist": True,
            "message": f"Pinned {sym.product_id} to watchlist",
        }


@router.delete("/{product_id}", response_model=dict[str, Any])
async def unpin_symbol(product_id: str) -> dict[str, Any]:
    """Unpin a symbol from the watchlist."""
    async with AsyncSessionLocal() as db:
        ok = await remove_from_watchlist(db, product_id.upper())
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol {product_id.upper()} not found in watchlist",
            )
        return {
            "product_id": product_id.upper(),
            "on_watchlist": False,
            "message": f"Removed {product_id.upper()} from watchlist",
        }

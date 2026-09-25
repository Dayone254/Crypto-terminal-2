"""Catalyst scraper — pulls dev activity, news, and volume surge data.

Data sources:
  * CoinGecko /coins/{id}          — developer_data (commits, PRs, stars)
  * CoinGecko /coins/markets       — 24h volume + price stats per batch
  * CryptoCompare /data/v2/news/   — latest articles filtered by coin keyword
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from tpt.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Coin symbol → CoinGecko ID mapping (common coins only; extended dynamically)
# ---------------------------------------------------------------------------
_SYMBOL_TO_CGID: dict[str, str] = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "AVAX-USD": "avalanche-2",
    "LINK-USD": "chainlink",
    "MATIC-USD": "matic-network",
    "POL-USD": "matic-network",
    "DOT-USD": "polkadot",
    "ADA-USD": "cardano",
    "XRP-USD": "ripple",
    "DOGE-USD": "dogecoin",
    "SHIB-USD": "shiba-inu",
    "UNI-USD": "uniswap",
    "AAVE-USD": "aave",
    "CRV-USD": "curve-dao-token",
    "MKR-USD": "maker",
    "SNX-USD": "synthetix-network-token",
    "COMP-USD": "compound-governance-token",
    "LDO-USD": "lido-dao",
    "OP-USD": "optimism",
    "ARB-USD": "arbitrum",
    "SUI-USD": "sui",
    "APT-USD": "aptos",
    "INJ-USD": "injective-protocol",
    "TIA-USD": "celestia",
    "SEI-USD": "sei-network",
    "NEAR-USD": "near",
    "FIL-USD": "filecoin",
    "ICP-USD": "internet-computer",
    "ATOM-USD": "cosmos",
    "ALGO-USD": "algorand",
    "TON-USD": "the-open-network",
    "FET-USD": "fetch-ai",
    "RNDR-USD": "render-token",
    "GRT-USD": "the-graph",
    "SAND-USD": "the-sandbox",
    "MANA-USD": "decentraland",
    "AXS-USD": "axie-infinity",
    "IMX-USD": "immutable-x",
    "LTC-USD": "litecoin",
    "BCH-USD": "bitcoin-cash",
    "ETC-USD": "ethereum-classic",
    "XLM-USD": "stellar",
    "VET-USD": "vechain",
    "HBAR-USD": "hedera-hashgraph",
    "FLOW-USD": "flow",
    "EOS-USD": "eos",
    "EGLD-USD": "elrond-erd-2",
    "RUNE-USD": "thorchain",
    "KSM-USD": "kusama",
    "ZEC-USD": "zcash",
    "DASH-USD": "dash",
    "XTZ-USD": "tezos",
    "IOTA-USD": "iota",
    "ONE-USD": "harmony",
    "WAVES-USD": "waves",
    "ENJ-USD": "enjincoin",
    "CHZ-USD": "chiliz",
    "BAT-USD": "basic-attention-token",
    "ZRX-USD": "0x",
    "1INCH-USD": "1inch",
    "SUSHI-USD": "sushi",
    "YFI-USD": "yearn-finance",
    "BAL-USD": "balancer",
    "REN-USD": "ren",
    "CELO-USD": "celo",
    "SKL-USD": "skale",
    "NMR-USD": "numeraire",
    "STORJ-USD": "storj",
    "ANKR-USD": "ankr",
    "OGN-USD": "origin-protocol",
    "LOOM-USD": "loom-network",
    "REP-USD": "augur",
}

# News keywords that indicate a high-impact catalyst
_CATALYST_KEYWORDS = [
    "mainnet", "launch", "upgrade", "partnership", "airdrop", "listing",
    "acquisition", "integration", "milestone", "release", "deploy",
    "protocol", "v2", "v3", "testnet", "bridge", "staking", "grant",
    "funding", "roadmap", "breakthrough", "record", "all-time",
]

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com"


@dataclass
class RawCatalystData:
    symbol: str
    coin_id: str
    commit_count_4w: int = 0
    pr_merged_4w: int = 0
    github_stars: int = 0
    github_forks: int = 0
    volume_24h: float = 0.0
    avg_volume_7d: float = 0.0
    volume_surge_ratio: float = 1.0
    price_change_24h: float = 0.0
    news_items: list[dict[str, Any]] = field(default_factory=list)
    catalyst_keywords_found: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None


def _make_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.coingecko_api_key:
        headers["x-cg-pro-api-key"] = settings.coingecko_api_key
    return headers


def _make_cc_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.cryptocompare_api_key:
        headers["authorization"] = f"Apikey {settings.cryptocompare_api_key}"
    return headers


def _resolve_coin_id(symbol: str) -> str | None:
    """Return CoinGecko ID for a Coinbase symbol like 'SOL-USD'."""
    return _SYMBOL_TO_CGID.get(symbol)


def _extract_keywords(text: str) -> list[str]:
    low = text.lower()
    return [kw for kw in _CATALYST_KEYWORDS if kw in low]


async def _fetch_dev_data(client: httpx.AsyncClient, coin_id: str) -> dict[str, Any]:
    """Fetch developer_data from CoinGecko /coins/{id}."""
    try:
        url = f"{_COINGECKO_BASE}/coins/{coin_id}"
        r = await client.get(
            url,
            params={"localization": "false", "tickers": "false", "market_data": "false",
                    "community_data": "false", "developer_data": "true", "sparkline": "false"},
            headers=_make_headers(),
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        dev = data.get("developer_data", {})
        return {
            "commit_count_4w": dev.get("commit_count_4_weeks", 0) or 0,
            "pr_merged_4w": dev.get("pull_requests_merged", 0) or 0,
            "github_stars": dev.get("stars", 0) or 0,
            "github_forks": dev.get("forks", 0) or 0,
        }
    except Exception as exc:
        logger.debug("[catalyst/scraper] dev_data failed for %s: %s", coin_id, exc)
        return {"commit_count_4w": 0, "pr_merged_4w": 0, "github_stars": 0, "github_forks": 0}


async def _fetch_market_data(
    client: httpx.AsyncClient, coin_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Fetch 24h volume + price change for a batch of coin IDs."""
    try:
        r = await client.get(
            f"{_COINGECKO_BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(coin_ids),
                "order": "market_cap_desc",
                "per_page": "250",
                "page": "1",
                "sparkline": "false",
                "price_change_percentage": "24h",
            },
            headers=_make_headers(),
            timeout=20.0,
        )
        r.raise_for_status()
        results: dict[str, dict[str, Any]] = {}
        for item in r.json():
            results[item["id"]] = {
                "volume_24h": item.get("total_volume") or 0.0,
                "price_change_24h": item.get("price_change_percentage_24h") or 0.0,
            }
        return results
    except Exception as exc:
        logger.debug("[catalyst/scraper] market_data batch failed: %s", exc)
        return {}


async def _fetch_news(
    client: httpx.AsyncClient, coin_symbol_base: str
) -> list[dict[str, Any]]:
    """Fetch latest news articles for a coin base symbol (e.g. 'SOL')."""
    try:
        r = await client.get(
            f"{_CRYPTOCOMPARE_BASE}/data/v2/news/",
            params={"categories": coin_symbol_base, "lTs": "0"},
            headers=_make_cc_headers(),
            timeout=15.0,
        )
        r.raise_for_status()
        data = r.json()
        articles = data.get("Data", [])[:5]
        return [
            {
                "title": a.get("title", ""),
                "source": a.get("source", ""),
                "url": a.get("url", ""),
                "published_at": a.get("published_on", 0),
            }
            for a in articles
        ]
    except Exception as exc:
        logger.debug("[catalyst/scraper] news failed for %s: %s", coin_symbol_base, exc)
        return []


async def fetch_batch(
    symbols: list[str],
    avg_volumes: dict[str, float] | None = None,
) -> list[RawCatalystData]:
    """Scrape catalyst data for a list of Coinbase symbols.

    Args:
        symbols: list of symbols like ['BTC-USD', 'ETH-USD']
        avg_volumes: optional precomputed 7-day average volumes keyed by symbol.
                     When absent, uses CoinGecko 24h volume as a proxy.
    """
    if avg_volumes is None:
        avg_volumes = {}

    # Resolve CoinGecko IDs — skip coins we don't have a mapping for
    id_map: dict[str, str] = {}  # symbol -> coin_id
    for sym in symbols:
        cid = _resolve_coin_id(sym)
        if cid:
            id_map[sym] = cid
        else:
            logger.debug("[catalyst/scraper] No CoinGecko ID for %s — skipping", sym)

    if not id_map:
        return []

    results: list[RawCatalystData] = []

    async with httpx.AsyncClient() as client:
        # 1. Market data for the whole batch (single request)
        coin_ids = list(id_map.values())
        market_data = await _fetch_market_data(client, coin_ids)

        # 2. Dev data + news per coin (respect free-tier rate limit with small delay)
        for sym, cid in id_map.items():
            try:
                dev_task = asyncio.create_task(_fetch_dev_data(client, cid))
                base_sym = sym.split("-")[0]
                news_task = asyncio.create_task(_fetch_news(client, base_sym))

                dev_data, news_items = await asyncio.gather(dev_task, news_task)

                mkt = market_data.get(cid, {})
                vol_24h = float(mkt.get("volume_24h") or 0.0)
                avg_vol = avg_volumes.get(sym, vol_24h)  # fallback to self if no history
                surge_ratio = (vol_24h / avg_vol) if avg_vol > 0 else 1.0

                # Extract catalyst keywords from all headlines
                all_text = " ".join(a.get("title", "") for a in news_items)
                kw_found = _extract_keywords(all_text)

                raw = RawCatalystData(
                    symbol=sym,
                    coin_id=cid,
                    commit_count_4w=dev_data["commit_count_4w"],
                    pr_merged_4w=dev_data["pr_merged_4w"],
                    github_stars=dev_data["github_stars"],
                    github_forks=dev_data["github_forks"],
                    volume_24h=vol_24h,
                    avg_volume_7d=avg_vol,
                    volume_surge_ratio=round(surge_ratio, 3),
                    price_change_24h=float(mkt.get("price_change_24h") or 0.0),
                    news_items=news_items,
                    catalyst_keywords_found=kw_found,
                )
                results.append(raw)
            except Exception as exc:
                logger.warning("[catalyst/scraper] Error scraping %s: %s", sym, exc)
                results.append(RawCatalystData(symbol=sym, coin_id=cid, error=str(exc)))

            # Small sleep to respect CoinGecko free-tier (50 req/min)
            await asyncio.sleep(0.3)

    return results

"""Catalyst analyzer — pure-function scorer for RawCatalystData.

Score breakdown:
    Volume Surge    [0, 40]  — ratio vs 7-day average
    Dev Activity    [0, 30]  — GitHub commits + PR merges
    Breaking News   [0, 20]  — high-impact keyword matches in headlines
    GitHub Stars    [0, 10]  — stars trending above coin's own baseline

Priority tiers:
    CRITICAL  ≥ 75
    HIGH      ≥ 55
    WATCH     ≥ 35
    NOISE     <  35
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from tpt.catalyst.scraper import RawCatalystData


@dataclass
class CatalystScore:
    symbol: str
    coin_id: str

    # Component scores
    volume_surge_score: float
    dev_activity_score: float
    news_score: float
    github_stars_score: float

    # Total
    catalyst_score: float
    priority_tier: str  # CRITICAL | HIGH | WATCH | NOISE

    # Key raw metrics (stored for display)
    volume_surge_ratio: float
    commit_count_4w: int
    pr_merged_4w: int
    github_stars: int
    top_headline: str | None
    catalyst_keywords_found: list[str]

    # Boost to inject into main scorer (0–15)
    scorer_boost: float


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_MAX_VOLUME_SURGE = 40.0
_MAX_DEV_ACTIVITY = 30.0
_MAX_NEWS = 20.0
_MAX_GITHUB_STARS = 10.0

# Volume thresholds
_VOL_SURGE_MIN = 1.5   # below this → 0 pts
_VOL_SURGE_MAX = 3.0   # at or above this → 40 pts

# Dev thresholds
_COMMIT_STRONG = 40    # 40+ commits → full dev points
_PR_STRONG = 10        # 10+ PRs merged → full PR points

# News: each distinct keyword match = 4 pts, capped at MAX
_NEWS_PTS_PER_KW = 4.0

# GitHub stars: above 10k is "notable", above 50k is "viral"
_STARS_NOTABLE = 10_000
_STARS_VIRAL = 50_000


def _score_volume_surge(ratio: float) -> float:
    if ratio < _VOL_SURGE_MIN:
        return 0.0
    if ratio >= _VOL_SURGE_MAX:
        return _MAX_VOLUME_SURGE
    # Linear interpolation between MIN and MAX
    t = (ratio - _VOL_SURGE_MIN) / (_VOL_SURGE_MAX - _VOL_SURGE_MIN)
    return round(_MAX_VOLUME_SURGE * t, 2)


def _score_dev_activity(commits: int, prs: int) -> float:
    # Commit component: 0→0, COMMIT_STRONG→25 pts (5 reserved for PRs)
    commit_score = min(25.0, 25.0 * (commits / _COMMIT_STRONG))
    # PR component: 0→0, PR_STRONG→5 pts
    pr_score = min(5.0, 5.0 * (prs / _PR_STRONG))
    return round(min(_MAX_DEV_ACTIVITY, commit_score + pr_score), 2)


def _score_news(keywords_found: list[str]) -> float:
    unique_kw = set(keywords_found)
    return round(min(_MAX_NEWS, len(unique_kw) * _NEWS_PTS_PER_KW), 2)


def _score_github_stars(stars: int) -> float:
    if stars <= 0:
        return 0.0
    if stars >= _STARS_VIRAL:
        return _MAX_GITHUB_STARS
    if stars >= _STARS_NOTABLE:
        # Log scale between NOTABLE and VIRAL
        t = math.log10(stars / _STARS_NOTABLE) / math.log10(_STARS_VIRAL / _STARS_NOTABLE)
        return round(_MAX_GITHUB_STARS * t, 2)
    return 0.0


def _tier(score: float) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 55:
        return "HIGH"
    if score >= 35:
        return "WATCH"
    return "NOISE"


def _boost_from_score(score: float) -> float:
    """Convert catalyst score [0, 100] to a scorer boost [0, 15]."""
    # Only HIGH and above contribute a boost; scale linearly 55→0pt, 100→15pt
    if score < 55:
        return 0.0
    return round(min(15.0, (score - 55.0) / (100.0 - 55.0) * 15.0), 2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score(raw: RawCatalystData) -> CatalystScore:
    """Score a RawCatalystData object and return a CatalystScore."""
    vol_score = _score_volume_surge(raw.volume_surge_ratio)
    dev_score = _score_dev_activity(raw.commit_count_4w, raw.pr_merged_4w)
    news_score = _score_news(raw.catalyst_keywords_found)
    stars_score = _score_github_stars(raw.github_stars)

    total = round(vol_score + dev_score + news_score + stars_score, 2)

    top_headline = None
    if raw.news_items:
        top_headline = raw.news_items[0].get("title")

    return CatalystScore(
        symbol=raw.symbol,
        coin_id=raw.coin_id,
        volume_surge_score=vol_score,
        dev_activity_score=dev_score,
        news_score=news_score,
        github_stars_score=stars_score,
        catalyst_score=total,
        priority_tier=_tier(total),
        volume_surge_ratio=raw.volume_surge_ratio,
        commit_count_4w=raw.commit_count_4w,
        pr_merged_4w=raw.pr_merged_4w,
        github_stars=raw.github_stars,
        top_headline=top_headline,
        catalyst_keywords_found=raw.catalyst_keywords_found,
        scorer_boost=_boost_from_score(total),
    )

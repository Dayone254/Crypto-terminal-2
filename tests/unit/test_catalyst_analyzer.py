"""Unit tests for the catalyst analyzer scoring logic."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from tpt.catalyst.analyzer import (
    CatalystScore,
    _score_dev_activity,
    _score_github_stars,
    _score_news,
    _score_volume_surge,
    _tier,
    score,
)
from tpt.catalyst.scraper import RawCatalystData


def _make_raw(**kwargs) -> RawCatalystData:
    defaults = dict(
        symbol="SOL-USD",
        coin_id="solana",
        commit_count_4w=0,
        pr_merged_4w=0,
        github_stars=0,
        github_forks=0,
        volume_24h=0.0,
        avg_volume_7d=0.0,
        volume_surge_ratio=1.0,
        price_change_24h=0.0,
        news_items=[],
        catalyst_keywords_found=[],
        fetched_at=datetime.now(timezone.utc),
        error=None,
    )
    defaults.update(kwargs)
    return RawCatalystData(**defaults)


# ---------------------------------------------------------------------------
# Component unit tests
# ---------------------------------------------------------------------------

class TestScoreVolumeSurge:
    def test_below_threshold_returns_zero(self):
        assert _score_volume_surge(1.0) == 0.0
        assert _score_volume_surge(1.49) == 0.0

    def test_at_min_threshold(self):
        assert _score_volume_surge(1.5) == 0.0

    def test_midpoint(self):
        # 2.25 is halfway between 1.5 and 3.0 → ~20 pts
        pts = _score_volume_surge(2.25)
        assert 18.0 <= pts <= 22.0

    def test_at_max_threshold(self):
        assert _score_volume_surge(3.0) == 40.0

    def test_above_max_capped(self):
        assert _score_volume_surge(5.0) == 40.0
        assert _score_volume_surge(10.0) == 40.0


class TestScoreDevActivity:
    def test_zero_activity(self):
        assert _score_dev_activity(0, 0) == 0.0

    def test_strong_commits_no_prs(self):
        # 40 commits → 25 pts, 0 PRs → 0 pts
        pts = _score_dev_activity(40, 0)
        assert pts == 25.0

    def test_strong_commits_and_prs(self):
        pts = _score_dev_activity(40, 10)
        assert pts == 30.0

    def test_partial_commits(self):
        # 20 commits = 50% of COMMIT_STRONG → 12.5 pts commit
        pts = _score_dev_activity(20, 0)
        assert abs(pts - 12.5) < 0.1

    def test_cap_at_30(self):
        # Even ridiculous values should cap at 30
        pts = _score_dev_activity(1000, 1000)
        assert pts == 30.0


class TestScoreNews:
    def test_no_keywords(self):
        assert _score_news([]) == 0.0

    def test_one_keyword(self):
        assert _score_news(["mainnet"]) == 4.0

    def test_multiple_unique_keywords(self):
        # 3 unique keywords × 4 = 12
        assert _score_news(["mainnet", "launch", "upgrade"]) == 12.0

    def test_duplicate_keywords_counted_once(self):
        # keyword set dedup: {"mainnet"} → 4 pts
        assert _score_news(["mainnet", "mainnet", "mainnet"]) == 4.0

    def test_cap_at_20(self):
        # 6 keywords × 4 = 24 → capped at 20
        kw = ["mainnet", "launch", "upgrade", "partnership", "airdrop", "listing"]
        assert _score_news(kw) == 20.0


class TestScoreGithubStars:
    def test_zero_stars(self):
        assert _score_github_stars(0) == 0.0

    def test_below_notable(self):
        assert _score_github_stars(5_000) == 0.0

    def test_at_notable(self):
        # Between 10k and 50k → some non-zero value but < 10
        pts = _score_github_stars(10_000)
        assert 0.0 <= pts < 10.0

    def test_at_viral(self):
        assert _score_github_stars(50_000) == 10.0

    def test_above_viral(self):
        assert _score_github_stars(200_000) == 10.0


class TestTier:
    def test_critical(self):
        assert _tier(75.0) == "CRITICAL"
        assert _tier(100.0) == "CRITICAL"

    def test_high(self):
        assert _tier(55.0) == "HIGH"
        assert _tier(74.9) == "HIGH"

    def test_watch(self):
        assert _tier(35.0) == "WATCH"
        assert _tier(54.9) == "WATCH"

    def test_noise(self):
        assert _tier(0.0) == "NOISE"
        assert _tier(34.9) == "NOISE"


# ---------------------------------------------------------------------------
# Integration: score() full pipeline
# ---------------------------------------------------------------------------

class TestScoreFunction:
    def test_all_zero_returns_noise(self):
        raw = _make_raw()
        cs = score(raw)
        assert isinstance(cs, CatalystScore)
        assert cs.priority_tier == "NOISE"
        assert cs.catalyst_score == 0.0
        assert cs.scorer_boost == 0.0

    def test_high_volume_surge_only(self):
        raw = _make_raw(volume_surge_ratio=3.0)
        cs = score(raw)
        assert cs.volume_surge_score == 40.0
        assert cs.priority_tier == "WATCH"   # 40 pts → WATCH

    def test_critical_threshold(self):
        # Volume surge 3x + strong dev + news  = critical
        raw = _make_raw(
            volume_surge_ratio=3.0,          # 40 pts
            commit_count_4w=40,              # 25 pts
            pr_merged_4w=10,                 # +5 → 30 total dev
            catalyst_keywords_found=["mainnet", "upgrade"],  # 8 pts
        )
        cs = score(raw)
        assert cs.catalyst_score >= 75.0
        assert cs.priority_tier == "CRITICAL"

    def test_scorer_boost_zero_for_noise(self):
        raw = _make_raw()
        cs = score(raw)
        assert cs.scorer_boost == 0.0

    def test_scorer_boost_positive_for_critical(self):
        raw = _make_raw(
            volume_surge_ratio=3.0,
            commit_count_4w=40,
            pr_merged_4w=10,
            catalyst_keywords_found=["mainnet", "upgrade"],
        )
        cs = score(raw)
        assert cs.scorer_boost > 0.0
        assert cs.scorer_boost <= 15.0

    def test_top_headline_extracted(self):
        raw = _make_raw(
            news_items=[
                {"title": "Solana launches staking upgrade", "source": "cointelegraph", "url": "http://example.com", "published_at": 0}
            ],
            catalyst_keywords_found=["launch", "upgrade"],
        )
        cs = score(raw)
        assert cs.top_headline == "Solana launches staking upgrade"

    def test_error_raw_still_scorable(self):
        """A raw with error=str should still score (defaults to zero metrics)."""
        raw = _make_raw(error="connection timeout")
        cs = score(raw)
        assert cs.priority_tier == "NOISE"

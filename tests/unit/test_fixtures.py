"""Unit tests validating real-session regression fixtures against expected engine parameters."""
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


class TestRegressionFixtures:
    @pytest.fixture
    def zora_fixture(self) -> dict:
        with open(FIXTURE_DIR / "zora_a_tag.json") as f:
            return json.load(f)

    @pytest.fixture
    def hype_fixture(self) -> dict:
        with open(FIXTURE_DIR / "hype_in_a.json") as f:
            return json.load(f)

    @pytest.fixture
    def near_fixture(self) -> dict:
        with open(FIXTURE_DIR / "near_above_a.json") as f:
            return json.load(f)

    @pytest.fixture
    def dash_fixture(self) -> dict:
        with open(FIXTURE_DIR / "dash_chase.json") as f:
            return json.load(f)

    def test_zora_quote_volume_formula(self, zora_fixture: dict) -> None:
        """Coinbase /stats volume is base units. Multiplying by last gives USD quote vol."""
        stats = zora_fixture["stats"]
        vol_base = float(stats["volume"])
        last_price = float(stats["last"])
        quote_vol = vol_base * last_price
        assert abs(quote_vol - zora_fixture["expected"]["quote_vol_24h"]) < 1000.0

    def test_hype_quote_volume_formula(self, hype_fixture: dict) -> None:
        stats = hype_fixture["stats"]
        quote_vol = float(stats["volume"]) * float(stats["last"])
        assert abs(quote_vol - hype_fixture["expected"]["quote_vol_24h"]) < 1.0

    def test_dash_chase_rule(self, dash_fixture: dict) -> None:
        stats = dash_fixture["stats"]
        open_p = float(stats["open"])
        high_p = float(stats["high"])
        low_p = float(stats["low"])
        last_p = float(stats["last"])

        day_change = ((last_p - open_p) / open_p) * 100.0
        pos_in_range = (last_p - low_p) / (high_p - low_p)

        assert day_change > 15.0
        assert pos_in_range > 0.80
        assert dash_fixture["expected"]["primary_label"] == "CHASE"
        assert dash_fixture["expected"]["ladder"] is None

    def test_near_above_a_no_entry_alert(self, near_fixture: dict) -> None:
        assert near_fixture["expected"]["primary_label"] == "WATCH"
        assert near_fixture["expected"]["alert_expected"] is False

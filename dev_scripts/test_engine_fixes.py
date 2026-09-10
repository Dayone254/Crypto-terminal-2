import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from tpt.engine.features import _compute_rsi
from tpt.engine.ladder import sanitize_ladder_dict
from tpt.engine.scorer import score


def test_rsi():
    # Downward trending prices: RSI should be low (< 30)
    closes = [100.0 - i * 1.0 for i in range(30)]
    rsi = _compute_rsi(closes, period=14)
    print(f"RSI Downward Trend: {rsi}")
    assert rsi is not None and rsi < 20.0, f"Expected low RSI on downtrend, got {rsi}"

    # Upward trending prices: RSI should be high (> 70)
    closes_up = [100.0 + i * 1.0 for i in range(30)]
    rsi_up = _compute_rsi(closes_up, period=14)
    print(f"RSI Upward Trend: {rsi_up}")
    assert rsi_up is not None and rsi_up > 80.0, f"Expected high RSI on uptrend, got {rsi_up}"
    print("✅ RSI Test Passed!")

def test_precision():
    lad = {
        "tranche_a_price": 0.000034,
        "stop_price": 0.000035,
        "target_1_price": 0.000032,
        "target_2_price": 0.000028
    }
    sanitized = sanitize_ladder_dict(lad)
    print(f"Sanitized Sub-Cent Ladder: {sanitized}")
    assert sanitized["stop_price"] > 0, "Stop price rounded to zero!"
    assert sanitized["target_1_price"] > 0, "Target 1 price rounded to zero!"
    print("✅ Precision Test Passed!")

def test_scorer_boundary():
    features = {"last_price": 100.0, "quote_vol_24h": 2_000_000.0}
    sc = score(features)
    print(f"Score at 2M Volume: {sc}")
    assert "LOW_VOLUME_PENALTY" in sc["components"], "Expected low volume penalty at 2M"
    print("✅ Scorer Boundary Test Passed!")

if __name__ == "__main__":
    test_rsi()
    test_precision()
    test_scorer_boundary()
    print("\n🎉 ALL ENGINE TESTS PASSED PERFECTLY!")

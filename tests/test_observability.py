from datetime import UTC, datetime, timedelta

from lakehouse.observability import evaluate_freshness, evaluate_volume


def test_volume_builds_a_baseline_before_judging():
    verdict = evaluate_volume("v", [5000, 5100], 10)
    assert verdict.passed
    assert "baseline" in verdict.message


def test_volume_within_threshold_passes():
    assert evaluate_volume("v", [5000, 5200, 4900, 5100], 5600).passed


def test_volume_collapse_is_flagged():
    verdict = evaluate_volume("v", [5000, 5200, 4900, 5100], 1200)
    assert not verdict.passed
    assert verdict.message.startswith("-7")


def test_volume_spike_is_flagged():
    assert not evaluate_volume("v", [100, 100, 100], 400).passed


def test_volume_uses_only_the_recent_window():
    history = [10] * 20 + [5000] * 7
    assert evaluate_volume("v", history, 5100).passed


def test_freshness_inside_and_outside_sla():
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    assert evaluate_freshness("f", now - timedelta(hours=2), now).passed
    assert not evaluate_freshness("f", now - timedelta(hours=30), now).passed
    assert not evaluate_freshness("f", None, now).passed


def test_freshness_treats_naive_timestamps_as_utc():
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    naive = datetime(2026, 10, 24, 11)
    assert evaluate_freshness("f", naive, now).observed == 1.0

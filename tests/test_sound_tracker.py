"""Sound radar behavior is source-verified and never invents rankings."""
import json
from datetime import datetime, timedelta, timezone

from scripts.update_sounds import build_snapshot, normalize_track


NOW = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)


def item(**changes):
    base = {
        "id": "sound-1", "platform": "tiktok", "title": "Original sound",
        "artist": "Creator", "region": "US",
        "source_url": "https://www.tiktok.com/music/123",
        "observed_at": NOW.isoformat(),
        "uses_24h": 250, "growth_24h_pct": 22.5, "rank": 2,
    }
    base.update(changes)
    return base


def test_unconfigured_source_produces_no_fabricated_sounds():
    snapshot = build_snapshot(now=NOW)
    assert snapshot["status"] == "feed_not_configured"
    assert snapshot["sounds"] == []
    assert snapshot["last_success_at"] is None


def test_provider_ranking_and_deduplication():
    tracks = [item(id="two", title="B", rank=1, uses_24h=1000),
              item(id="one", title="A", rank=3),
              item(id="two", title="B", rank=1, uses_24h=1000)]
    snap = build_snapshot(now=NOW, url="https://partner.example/sounds",
        fetch=lambda url, token: json.dumps({"source": "Partner", "sounds": tracks}).encode())
    assert snap["status"] == "ok"
    assert snap["source"] == "Partner"
    assert [s["id"] for s in snap["sounds"]] == ["two", "one"]
    assert snap["sound_count"] == 2


def test_reject_invalid_sources_and_old_observations():
    assert normalize_track(item(source_url="http://unsafe.test/s"), NOW) is None
    assert normalize_track(item(observed_at=(NOW - timedelta(days=15)).isoformat()), NOW) is None
    assert normalize_track(item(platform="unlisted"), NOW) is None
    assert normalize_track(item(uses_24h=-200), NOW)["uses_24h"] is None


def test_failed_feed_preserves_last_known_verified_data():
    prior = {"source":"Partner", "last_success_at":"2026-11-16T10:00:00+00:00", "sounds":[item()]}
    def failing(url, token):
        raise TimeoutError("timeout")
    snap = build_snapshot(now=NOW, previous=prior,
                          url="https://partner.example/sounds", fetch=failing)
    assert snap["status"] == "feed_error"
    assert len(snap["sounds"]) == 1
    assert snap["last_success_at"] == prior["last_success_at"]

"""Refresh licensed, timestamped social-audio rankings for the static dashboard.

The official creator APIs do not expose a cross-platform 'most viral sounds' chart.
Connect an approved JSON feed; never synthesize tracks or performance numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

PLATFORMS = {"tiktok", "instagram", "youtube", "facebook", "x"}
MAX_SOUNDS = 120


def https_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2000:
        return ""
    try:
        url = urlsplit(value.strip())
        if url.scheme == "https" and url.hostname and not url.username and not url.password:
            return value.strip()
    except ValueError:
        pass
    return ""


def text(value: object, limit: int = 140) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def number(value: object, *, integer: bool = False):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        value = float(value)
        if not (-1e12 < value < 1e12) or value != value:
            return None
        if integer:
            return int(value) if value >= 0 else None
        return round(value, 2)
    except (ValueError, TypeError, OverflowError):
        return None


def iso_datetime(value: object, now: datetime):
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        d = d.astimezone(timezone.utc)
        if d > now + timedelta(hours=1) or d < now - timedelta(days=14):
            return None
        return d
    except ValueError:
        return None


def normalize_track(item: object, now: datetime):
    if not isinstance(item, dict):
        return None
    platform = text(item.get("platform"), 24).lower()
    title = text(item.get("title"), 160)
    artist = text(item.get("artist"), 120) or "Unknown creator"
    source_url = https_url(item.get("source_url"))
    observed = iso_datetime(item.get("observed_at"), now)
    if platform not in PLATFORMS or not title or not source_url or not observed:
        return None
    return {
        "id": text(item.get("id"), 100) or (platform + ":" + title.casefold() + ":" + artist.casefold()),
        "platform": platform,
        "title": title,
        "artist": artist,
        "region": text(item.get("region"), 24).upper() or "GLOBAL",
        "observed_at": observed.isoformat(),
        "source_url": source_url,
        "preview_url": https_url(item.get("preview_url")),
        "rank": number(item.get("rank"), integer=True),
        "uses_24h": number(item.get("uses_24h"), integer=True),
        "total_uses": number(item.get("total_uses"), integer=True),
        "growth_24h_pct": number(item.get("growth_24h_pct")),
    }


def _fetch(url: str, token: str) -> bytes:
    headers = {"Accept": "application/json", "User-Agent": "ViralForge-SoundRadar/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError("Sound provider did not return HTTP 200")
        body = response.read(1_000_001)
    if len(body) > 1_000_000:
        raise ValueError("Sound provider response is too large")
    return body


def build_snapshot(*, fetch=None, now=None, previous=None, url="", token=""):
    now = now or datetime.now(timezone.utc)
    previous = previous if isinstance(previous, dict) else {}
    previous_tracks = previous.get("sounds", [])
    if not isinstance(previous_tracks, list):
        previous_tracks = []
    result = {
        "checked_at": now.isoformat(),
        "last_success_at": previous.get("last_success_at"),
        "status": "feed_not_configured",
        "source": text(previous.get("source"), 120) or "No approved sound chart connected",
        "sound_count": 0,
        "sounds": previous_tracks[:MAX_SOUNDS],
        "error": None,
        "cadence_hours": 8,
        "disclaimer": "Source-reported observations, not independent or guaranteed platform-wide rankings.",
    }
    if not https_url(url):
        result["sound_count"] = len(result["sounds"])
        return result

    try:
        data = json.loads((fetch or _fetch)(url, token))
        if isinstance(data, list):
            raw = data
            provider = "Approved sound chart"
        elif isinstance(data, dict):
            raw = data.get("sounds", data.get("tracks"))
            provider = text(data.get("source"), 120) or (urlsplit(url).hostname or "Approved sound chart")
        else:
            raise ValueError("Expected JSON with a sounds array")
        if not isinstance(raw, list):
            raise ValueError("Provider must return a sounds or tracks array")
        unique = {}
        for row in raw[:2000]:
            sound = normalize_track(row, now)
            if sound is None:
                continue
            key = (sound["platform"], sound["id"])
            if key not in unique or sound["observed_at"] > unique[key]["observed_at"]:
                unique[key] = sound
        tracks = list(unique.values())
        if not tracks:
            raise ValueError("No valid, dated sound observations from provider")
        # Respect an explicit provider rank where supplied, otherwise sort by measurable growth/usage.
        tracks.sort(key=lambda s: (
            s["rank"] is None,
            s["rank"] if s["rank"] is not None else 999999,
            -(s["growth_24h_pct"] if s["growth_24h_pct"] is not None else -1e8),
            -(s["uses_24h"] if s["uses_24h"] is not None else -1),
        ))
        result.update(
            status="ok",
            source=provider,
            last_success_at=now.isoformat(),
            sounds=tracks[:MAX_SOUNDS],
            sound_count=min(len(tracks), MAX_SOUNDS),
        )
    except (OSError, TimeoutError, ValueError, TypeError, json.JSONDecodeError) as exc:
        result["status"] = "feed_error"
        result["error"] = type(exc).__name__ + ": " + text(str(exc), 100)
        result["sound_count"] = len(result["sounds"])
    return result


def main():
    parser = argparse.ArgumentParser(description="Update authorized social sound observations")
    parser.add_argument("--output", default="data/trend_sounds.json")
    args = parser.parse_args()
    path = Path(args.output)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    snapshot = build_snapshot(
        previous=previous,
        url=os.getenv("SOUND_FEED_URL", ""),
        token=os.getenv("SOUND_FEED_BEARER_TOKEN", ""),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Sound radar: {snapshot['status']} / {snapshot['sound_count']} observed sounds")


if __name__ == "__main__":
    main()

"""Evidence-aware editing recommendations from browser-measured video signals.

The browser measures frames/audio locally and sends only numeric summaries on request.
These features are sampled proxies, not semantic understanding or proprietary ranking data.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field
from .creative_coach import PLATFORM_RULES

TargetPlatform = Literal["tiktok", "instagram", "x", "facebook", "youtube"]
Goal = Literal["reach", "engagement", "leads", "sales"]


class VideoSignals(BaseModel):
    platform: TargetPlatform
    goal: Goal = "reach"
    duration_seconds: float = Field(ge=0.1, le=7200)
    frame_samples: int = Field(ge=2, le=60)
    mean_brightness: float = Field(ge=0, le=1)
    opening_contrast: float = Field(ge=0, le=1)
    mean_frame_change: float = Field(ge=0, le=1)
    sampled_change_events: int = Field(ge=0, le=60)
    quiet_segment_fraction: float | None = Field(default=None, ge=0, le=1)
    near_peak_fraction: float | None = Field(default=None, ge=0, le=1)
    sample_interval_seconds: float = Field(ge=0.01, le=7200)
    first_change_at_seconds: float | None = Field(default=None, ge=0, le=7200)


def recommendations_from_signals(signals: VideoSignals) -> dict:
    evidence = [
        {"label": "Sampled frames", "value": signals.frame_samples, "unit": "frames"},
        {"label": "Mean image brightness", "value": round(signals.mean_brightness, 3), "unit": "normalized"},
        {"label": "Opening visual contrast", "value": round(signals.opening_contrast, 3), "unit": "normalized"},
        {"label": "Adjacent sampled frame change", "value": round(signals.mean_frame_change, 3), "unit": "normalized"},
    ]
    experiments = []
    def add(focus: str, finding: str, edit: str, metric: str) -> None:
        experiments.append({"focus": focus, "observed_signal": finding, "suggestion": edit, "validation_metric": metric})

    if signals.opening_contrast < 0.13:
        add("Opening visibility", "Low contrast in the sampled opening frame.",
            "Check whether the subject or key text stands out on a phone. Test a brighter opening, stronger subject separation, or a cleaner first shot.",
            "First 3-second retention")
    else:
        add("Opening experiment", "Opening contrast is measurable; narrative clarity was not assessed.",
            "Compare an opening that shows the payoff with an opening that poses a precise question.",
            "First 3-second retention")

    if signals.mean_brightness < 0.26:
        add("Mobile legibility", "Low average brightness across sampled frames.",
            "Review the video at low screen brightness. If important details disappear, brighten them selectively or strengthen captions.",
            "Completion rate and qualitative viewer feedback")

    if signals.sampled_change_events >= max(3, int(signals.frame_samples * 0.55)):
        add("Visual pacing", "Frequent large differences between the sampled frames.",
            "The edit may be visually busy. Test holding key proof or payoff shots slightly longer.",
            "Average view duration and completion rate")
    elif signals.mean_frame_change < 0.11 and signals.duration_seconds >= 8:
        add("Visual pacing", "Low differences across sampled frames.",
            "Test a purposeful angle, demonstration, insert, or text change around a flat section; don't add cuts without a reason.",
            "Average view duration and retention dips")

    if signals.first_change_at_seconds is not None and signals.first_change_at_seconds > 3:
        add("Early variation", "The first substantial sampled visual change occurs after 3 seconds.",
            "Try an earlier payoff shot, clearer title treatment, or relevant camera change.",
            "First 3- and 5-second retention")

    if signals.quiet_segment_fraction is not None:
        evidence.append({"label": "Low-energy audio windows", "value": round(signals.quiet_segment_fraction, 3), "unit": "share of sampled windows"})
        if signals.quiet_segment_fraction > 0.3:
            add("Sound design", "Several audio windows have low energy.",
                "Check whether the quiet passages are intentional. Test trimming unnecessary pauses or improving dialogue audibility.",
                "Audience retention around quiet passages")
    if signals.near_peak_fraction is not None:
        evidence.append({"label": "Near-peak audio samples", "value": round(signals.near_peak_fraction, 4), "unit": "fraction"})
        if signals.near_peak_fraction > 0.02:
            add("Audio headroom", "Many sampled values approach maximum digital amplitude.",
                "Review for clipping and reduce gain or apply a limiter when needed.",
                "Manual headphone review and viewer feedback")

    platform = PLATFORM_RULES[signals.platform]
    for focus, edit, metric in platform[:2]:
        add(focus, "Platform-specific creative hypothesis, not observed footage semantics.", edit, metric)
    if signals.goal in ("sales", "leads"):
        add("Conversion handoff", "Conversion is the selected campaign goal.",
            "Place one specific next step after the demonstrated benefit and tag the landing page for attribution.",
            "Qualified conversions per 1,000 views")

    return {
        "platform": signals.platform,
        "evidence_level": "locally_sampled_video_signal_summary",
        "measurements": evidence,
        "experiments": experiments,
        "caveat": "Measured visual brightness and frame differences are not semantic recognition, exact edit detection, or private platform metrics. Audio-energy statistics cannot identify words. Advice is testable, never a guaranteed ranking trigger.",
    }

from fastapi.testclient import TestClient
from viralforge.video_signals import VideoSignals, recommendations_from_signals
from viralforge.app import app

def base(platform="tiktok"):
    return dict(platform=platform,duration_seconds=18,frame_samples=12,
                mean_brightness=.2,opening_contrast=.09,
                mean_frame_change=.06,sampled_change_events=1,
                sample_interval_seconds=1.4,quiet_segment_fraction=.45,
                near_peak_fraction=.0,first_change_at_seconds=4.2)

def test_video_signal_recommendations_have_observed_evidence():
    result=recommendations_from_signals(VideoSignals(**base()))
    names={r["focus"] for r in result["experiments"]}
    assert {"Opening visibility","Mobile legibility","Visual pacing","Sound design","Early variation"} <= names
    assert result["evidence_level"]=="locally_sampled_video_signal_summary"
    assert "not" in result["caveat"]

def test_each_platform_has_distinct_editing_focus():
    first={platform:recommendations_from_signals(VideoSignals(**base(platform)))["experiments"][-2]["focus"]
           for platform in ("tiktok","instagram","x","facebook","youtube")}
    assert len(set(first.values()))==5

def test_audio_is_not_invented_when_not_decoded():
    d=base()
    d["quiet_segment_fraction"]=None
    d["near_peak_fraction"]=None
    report=recommendations_from_signals(VideoSignals(**d))
    assert not any("audio" in m["label"].lower() for m in report["measurements"])
    assert not any(x["focus"] == "Sound design" for x in report["experiments"])

def test_signal_schema_rejects_invalid_ranges():
    from pydantic import ValidationError
    d=base();d["mean_brightness"]=1.9
    try: VideoSignals(**d)
    except ValidationError: pass
    else: raise AssertionError("invalid brightness was accepted")

def test_api_rejects_unauthed_signal_submission():
    client=TestClient(app)
    response=client.post("/api/video-signals/plan",json=base())
    assert response.status_code==401

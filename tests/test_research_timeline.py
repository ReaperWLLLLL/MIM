"""Exact WAV timing and frozen-input invalidation (no synthesized test voice)."""
import copy
import hashlib
import importlib
from pathlib import Path
import sys
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research.spec import content_hash
from voice_fixture import bind_audio


def api():
    try:
        return importlib.import_module("research.timeline")
    except ModuleNotFoundError:
        pytest.fail("research.timeline has not been implemented")


@pytest.fixture
def inputs(tmp_path):
    spec = {"project": {"title": "采样"}, "slides": [
        {"id": "s1", "screen_text": {"title": "测量"}, "beats": [
            {"id": "a", "narration": "测量输入。", "screen_text": ["title"]},
            {"id": "b", "narration": "比较输出。", "screen_text": ["title"]}]},
        {"id": "s2", "screen_text": {"title": "误差"}, "beats": [
            {"id": "a", "narration": "检查误差。", "screen_text": ["title"]}]}]}
    audio = {"job_id": "fixture", "settings": {}, "audio": []}
    for i, (slide, beat, samples) in enumerate([
        (spec["slides"][0], spec["slides"][0]["beats"][0], 401),
        (spec["slides"][0], spec["slides"][0]["beats"][1], 400),
        (spec["slides"][1], spec["slides"][1]["beats"][0], 1),
    ]):
        path = tmp_path / f"{i}.wav"
        with wave.open(str(path), "wb") as out:
            out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            out.writeframes(b"\x01\x00" * samples)
        audio["audio"].append({"slide_id": slide["id"], "beat_id": beat["id"],
            "path": str(path), "sample_rate": 24000, "sample_count": samples,
            "samples": samples, "duration": 999, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "spoken_text": beat["narration"], "narration": beat["narration"],
            "text_hash": content_hash(beat["narration"]), "narration_hash": content_hash(beat["narration"])})
    bind_audio(spec, audio)
    return spec, audio


@pytest.mark.parametrize("key,value", [("model", "other"), ("speaker", "Ryan"),
    ("language", "English"), ("instruct", "不同语气"), ("pronunciation", {"输入": "输出"}),
    ("generation", {"do_sample": True}), ("seed", 9)])
def test_fresh_timeline_rejects_changed_synthesis_request(inputs, key, value):
    spec, audio = inputs
    spec["voice"][key] = value
    with pytest.raises(ValueError, match="voice|synthesis"):
        api().build_timeline(spec, audio, 60)


@pytest.mark.parametrize("change", ["revision", "job", "cue"])
def test_offline_audio_identity_is_validated(inputs, change):
    spec, audio = inputs
    if change == "revision":
        audio["settings"]["revision"] = "unverified"
    elif change == "job":
        audio["job_id"] = "0" * 64
    else:
        audio["audio"][0]["cache_key"] = "0" * 64
    with pytest.raises(ValueError, match="identity|job|cue"):
        api().build_timeline(spec, audio, 60)


def test_observation_only_voice_changes_keep_audio_admissible(inputs):
    spec, audio = inputs
    spec["voice"].update(observation_timeout=1, poll_interval=99, host="different")
    assert api().build_timeline(spec, audio, 60)["total_frames"] == 4


def test_offline_timeline_rejects_nonempty_silent_wav(inputs):
    spec, audio = inputs
    cue = audio["audio"][0]
    path = Path(cue["path"])
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(bytes(cue["sample_count"] * 2))
    cue["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="signal|silent"):
        api().build_timeline(spec, audio, 60)


def test_samples_round_up_and_half_open_intervals_are_contiguous(inputs):
    spec, audio = inputs
    timeline = api().build_timeline(spec, audio, 60)
    assert timeline["total_frames"] == 4
    assert [(s["start_frame"], s["end_frame"]) for s in timeline["slides"]] == [(0, 3), (3, 4)]
    assert [(b["start_frame"], b["end_frame"]) for s in timeline["slides"] for b in s["beats"]] == [(0, 2), (2, 3), (3, 4)]
    assert timeline["slides"][0]["beats"][0]["sample_count"] == 401
    assert timeline["slides"][0]["beats"][0]["duration_seconds"] == 2 / 60
    assert api().validate_timeline(timeline, spec, audio, 60) == []


def test_build_does_not_mutate_input_and_rejects_declared_sample_lie(inputs):
    spec, audio = inputs
    original = copy.deepcopy((spec, audio))
    api().build_timeline(spec, audio, 60)
    assert (spec, audio) == original
    audio["audio"][0]["sample_count"] = 400
    with pytest.raises(ValueError, match="sample_count"):
        api().build_timeline(spec, audio, 60)


@pytest.mark.parametrize("fps", [0, -1, 60.1, True])
def test_invalid_fps_cannot_make_negative_intervals(inputs, fps):
    with pytest.raises(ValueError, match="fps"):
        api().build_timeline(*inputs, fps)


@pytest.mark.parametrize("change", ["screen", "narration", "audio_bytes", "audio_hash", "interval", "fps", "settings"])
def test_frozen_timeline_rejects_changed_text_audio_or_structure(inputs, change):
    spec, audio = inputs
    timeline = api().build_timeline(spec, audio, 60)
    fps = 60
    if change == "screen":
        spec["slides"][0]["screen_text"]["title"] = "新的测量"
    elif change == "narration":
        spec["slides"][0]["beats"][0]["narration"] = "新的讲稿。"
    elif change == "audio_bytes":
        path = Path(audio["audio"][0]["path"])
        data = path.read_bytes()
        path.write_bytes(data[:-2] + b"\x02\x00")
    elif change == "audio_hash":
        audio["audio"][0]["sha256"] = "0" * 64
    elif change == "interval":
        timeline["slides"][0]["beats"][0]["end_frame"] = 0
    elif change == "fps":
        fps = 15
    else:
        audio["settings"]["speaker"] = "different"
    assert api().validate_timeline(timeline, spec, audio, fps)


@pytest.mark.parametrize("change", ["duplicate", "missing", "extra", "empty", "truncated"])
def test_invalid_audio_inventory_fails_closed(inputs, change):
    spec, audio = inputs
    if change == "duplicate":
        audio["audio"].append(copy.deepcopy(audio["audio"][0]))
    elif change == "missing":
        audio["audio"].pop()
    elif change == "extra":
        extra = copy.deepcopy(audio["audio"][0]); extra["beat_id"] = "unknown"
        audio["audio"].append(extra)
    elif change == "empty":
        spec["slides"] = []
    else:
        path = Path(audio["audio"][0]["path"])
        path.write_bytes(path.read_bytes()[:-2])
        audio["audio"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        api().build_timeline(spec, audio, 60)

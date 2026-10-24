"""Freeze verified PCM WAV sample counts into contiguous half-open video frames.

Every beat is ceil(sample_count * fps / sample_rate) frames. Rounding padding
belongs at the END of that beat; Task 5 must not concatenate raw audio without
this padding. Global frame positions are integers; seconds are informational.
No character-count timing, model loading, or declared-duration trust is used.
"""
from __future__ import annotations

import hashlib
import copy
from pathlib import Path
import wave

from .spec import content_hash
from .voice import validate_audio_identity
from .remote_worker import require_pcm_signal


def require_narrated(spec, *artifacts):
    """Reject preview contracts before a narrated consumer reads voice identity."""
    if spec.get("schema_version") == "research-preview-spec-1":
        raise ValueError("narrated workflow does not accept silent-preview specs")
    for artifact in artifacts:
        if (isinstance(artifact, dict) and
                (artifact.get("mode") not in (None, "narrated")
                 or str(artifact.get("schema_version", "")).startswith(("research-preview-", "research-authored-")))):
            raise ValueError("narrated workflow does not accept silent-preview artifacts")


def _positive_int(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name}: must be a positive integer")
    return value


def _verified_audio(item, beat):
    path = Path(item["path"])
    if not path.is_absolute():
        raise ValueError("audio.path must be absolute")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        raise ValueError(f"audio.sha256 mismatch: {path}")
    with wave.open(str(path), "rb") as wav:
        rate, count = wav.getframerate(), wav.getnframes()
        width, channels = wav.getsampwidth(), wav.getnchannels()
        payload = wav.readframes(count)
        if wav.getcomptype() != "NONE" or len(payload) != count * width * channels:
            raise ValueError(f"truncated or non-PCM WAV: {path}")
        require_pcm_signal(payload, width)
    _positive_int(count, "WAV sample_count")
    _positive_int(rate, "WAV sample_rate")
    for key, actual in (("sample_count", count), ("sample_rate", rate)):
        if _positive_int(item[key], key) != actual:
            raise ValueError(f"audio.{key} differs from verified WAV")
    if "samples" in item and item["samples"] != count:
        raise ValueError("audio.samples alias differs from sample_count")
    narration = beat["narration"]
    if (item["narration"] != narration or item["narration_hash"] != content_hash(narration)
            or item["text_hash"] != content_hash(item["spoken_text"])):
        raise ValueError("audio narration/text_hash is stale")
    return {"path": str(path.resolve()), "sha256": digest, "sample_count": count,
            "sample_rate": rate, "channels": channels, "sample_width": width,
            "narration_hash": item["narration_hash"], "text_hash": item["text_hash"]}


def build_timeline(spec: dict, audio: dict, fps: int) -> dict:
    """Return a frozen v1 timeline or ValueError; read and verify every local WAV.

    Audio is synthesize_remote's manifest. A different spec, audio settings/hash,
    WAV, fps or altered frame interval invalidates validate_timeline. Paths and
    all hashes are retained for downstream sample-accurate assembly and QA.
    """
    require_narrated(spec, audio)
    _positive_int(fps, "fps")
    try:
        validate_audio_identity(spec, audio)
        inventory = {}
        for item in audio["audio"]:
            key = (item["slide_id"], item["beat_id"])
            if key in inventory:
                raise ValueError(f"duplicate audio beat {key}")
            inventory[key] = item
        slides, cursor, used, slide_ids = [], 0, set(), set()
        for slide in spec["slides"]:
            sid = slide["id"]
            if sid in slide_ids:
                raise ValueError(f"duplicate slide {sid}")
            slide_ids.add(sid)
            start, beats = cursor, []
            for beat in slide["beats"]:
                key = (sid, beat["id"])
                if key in used or key not in inventory:
                    raise ValueError(f"duplicate or missing beat {key}")
                used.add(key)
                verified = _verified_audio(inventory[key], beat)
                samples, rate = verified["sample_count"], verified["sample_rate"]
                frames = (samples * fps + rate - 1) // rate
                beats.append({"id": beat["id"], "slide_id": sid,
                              "start_frame": cursor, "end_frame": cursor + frames,
                              "local_start_frame": cursor - start,
                              "local_end_frame": cursor + frames - start,
                              "frames": frames, "duration_seconds": frames / fps,
                              "audio_duration_seconds": samples / rate,
                              "padding_seconds": (frames * rate - samples * fps) / (fps * rate),
                              **verified})
                cursor += frames
            if not beats:
                raise ValueError(f"slide {sid} has no beats")
            slides.append({"id": sid, "start_frame": start, "end_frame": cursor,
                           "frames": cursor - start, "beats": beats})
        if not slides or used != set(inventory):
            raise ValueError("empty slides or extra audio inventory")
        result = {"schema_version": "research-timeline-1", "fps": fps,
                  "audio_identity": copy.deepcopy({"job_id": audio["job_id"], "settings": audio["settings"],
                      "audio": [{k: item[k] for k in ("slide_id", "beat_id", "file", "cache_key", "narration", "spoken_text")}
                                for item in audio["audio"]]}),
                  "spec_hash": content_hash(spec),
                  "audio_hash": content_hash({"job_id": audio.get("job_id"),
                      "settings": audio.get("settings"),
                      "beats": [{k: b[k] for k in ("slide_id", "id", "path", "sha256", "sample_count", "sample_rate", "narration_hash", "text_hash")}
                                for s in slides for b in s["beats"]]}),
                  "total_frames": cursor, "duration_seconds": cursor / fps,
                  "slides": slides}
        result["timeline_hash"] = content_hash(result)
        return result
    except (KeyError, TypeError, OSError, wave.Error, EOFError) as exc:
        raise ValueError(f"invalid timeline input: {exc}") from exc


def validate_timeline(timeline: dict, spec: dict, audio: dict, fps: int) -> list[str]:
    """Revalidate bytes and exact structure, not only the stored digest."""
    try:
        require_narrated(spec, timeline, audio)
        if timeline.get("schema_version") != "research-timeline-1":
            raise ValueError("narrated workflow requires research-timeline-1")
        expected = build_timeline(spec, audio, fps)
    except ValueError as exc:
        return [str(exc)]
    return [] if timeline == expected else ["frozen timeline is stale or altered; rebuild from current spec, WAVs and fps"]

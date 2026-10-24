"""Stdlib-only SSH TTS client. No model/package downloader runs on the client.

An observation timeout is not a job failure: repeat synthesize_remote with the
same text/settings to observe the same persistent remote job, never resubmit it.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time

from .spec import content_hash
from .remote_worker import audio_metadata


class VoiceObservationTimeout(TimeoutError):
    def __init__(self, job_id):
        self.job_id = job_id
        super().__init__(f"Still observing remote voice job {job_id}; repeat the same request to resume")


def voice_job_id(texts: list[dict], settings: dict) -> str:
    return content_hash({"protocol": 1, "texts": texts, "settings": settings})


def synthesis_settings(voice):
    """Synthesis semantics only; transport and observation do not change speech."""
    return {"model": voice["model"], "speaker": voice["speaker"],
            "language": voice.get("language", "Chinese"),
            "instruct": voice.get("instruct", "用沉稳、清晰的普通话讲解科研内容，语速适中，术语之间自然停顿。"),
            "pronunciation": voice.get("pronunciation", {}),
            "generation": voice.get("generation", {"do_sample": False, "max_new_tokens": 2048}),
            "seed": voice.get("seed", 0)}


def voice_texts(spec, settings):
    texts = []
    for slide in spec["slides"]:
        for beat in slide.get("beats", []):
            narration = beat.get("narration", "")
            if not isinstance(narration, str) or not narration.strip():
                raise ValueError("Each voice beat requires nonempty final narration")
            spoken = narration
            for original, replacement in settings["pronunciation"].items():
                if not isinstance(original, str) or not original or not isinstance(replacement, str):
                    raise ValueError("pronunciation must map nonempty strings to strings")
                spoken = spoken.replace(original, replacement)
            texts.append({"slide_id": slide["id"], "beat_id": beat["id"],
                          "text": spoken, "narration": narration})
    if not texts:
        raise ValueError("No voice beats")
    return texts


def validate_audio_identity(spec, audio):
    """Offline admission: retain model-content/job/cue provenance, never contact SSH."""
    wanted, recorded = synthesis_settings(spec["voice"]), audio["settings"]
    if any(recorded.get(k) != v for k, v in wanted.items()):
        raise ValueError("audio synthesis settings differ from current voice request")
    if (not re.fullmatch(r"sha256:[a-f0-9]{64}", recorded.get("revision", ""))
            or not PurePosixPath(recorded.get("model_path", "")).is_absolute()):
        raise ValueError("audio model-content identity is missing or invalid")
    texts = voice_texts(spec, wanted)
    if audio.get("job_id") != voice_job_id(texts, recorded):
        raise ValueError("audio job identity mismatch")
    if len(audio["audio"]) != len(texts):
        raise ValueError("audio cue inventory mismatch")
    cache_settings = {k: v for k, v in recorded.items() if k not in {"gpu", "model_path"}}
    for index, (cue, text) in enumerate(zip(audio["audio"], texts)):
        key = content_hash({"protocol": 1, "text": text["text"], "settings": cache_settings})
        if (cue.get("cache_key") != key or cue.get("file") != f"{index:04d}.wav"
                or any(cue.get(k) != text[k] for k in ("slide_id", "beat_id", "narration"))
                or cue.get("spoken_text") != text["text"]):
            raise ValueError("audio cue identity/text mismatch")


def validate_transport(settings):
    if settings.get("backend") != "ssh":
        raise ValueError("Only backend=ssh is supported; local TTS is forbidden")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", settings.get("host", "")):
        raise ValueError("host must be an SSH alias")
    root = settings.get("remote_root", "")
    parts = PurePosixPath(root).parts
    if (not root.startswith("/") or ".." in parts or "\\" in root or "\x00" in root
            or len(parts) < 2 or root in {"/root", "/var/root", "/home", "/Users"}
            or parts[1] in {"home", "Users"} and len(parts) <= 3):
        raise ValueError("remote_root must be a scoped absolute data directory")


def ssh(settings, args, payload=b"", *, timeout=30):
    """Quote the remote shell boundary once; never use a local shell or SCP glob."""
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "--", settings["host"], shlex.join(args)],
                          input=payload, capture_output=True, check=True, timeout=timeout).stdout


def deploy_worker(settings):
    validate_transport(settings)
    source = Path(__file__).with_name("remote_worker.py").read_bytes()
    bootstrap = ("import os,pathlib,sys,tempfile; r=pathlib.Path(sys.argv[1]); "
                 "r.mkdir(parents=True,exist_ok=True); "
                 "fd,p=tempfile.mkstemp(dir=r,prefix='worker-',suffix='.tmp'); "
                 "f=os.fdopen(fd,'wb'); f.write(sys.stdin.buffer.read()); f.close(); "
                 "os.replace(p,r/'remote_worker.py')")
    ssh(settings, ["python3", "-c", bootstrap, settings["remote_root"]], source)


def request(settings, action, payload=None):
    remote = settings["remote_root"]
    raw = ssh(settings, [remote + "/venv/bin/python", remote + "/remote_worker.py",
                         "--root", remote, "--action", action],
              json.dumps(payload or {}, ensure_ascii=False, allow_nan=False).encode())
    return raw if action == "audio" else json.loads(raw)


def synthesize_remote(spec: dict, root: Path) -> dict:
    voice = spec["voice"]
    validate_transport(voice)
    # Deployment transfers Python source only, never a model or dependency.
    deploy_worker(voice)
    identity = request(voice, "identity")
    if identity["model_id"] != voice["model"]:
        raise ValueError("Requested model does not match the remote manifest")
    settings = {**synthesis_settings(voice), "revision": identity["identity"],
                "model_path": identity["model_path"], "gpu": voice.get("gpu", 0)}
    texts = voice_texts(spec, settings)
    job_id = voice_job_id(texts, settings)
    payload = {"job_id": job_id}

    def observe(action, data):
        try:
            return request(voice, action, data)
        except subprocess.TimeoutExpired as error:
            raise VoiceObservationTimeout(job_id) from error

    status = observe("status", payload)
    if status["state"] == "missing":
        status = observe("submit", dict(payload, texts=texts, settings=settings))
    deadline = time.monotonic() + voice.get("observation_timeout", 60)
    while status["state"] in {"running", "queued"}:
        if time.monotonic() >= deadline:
            raise VoiceObservationTimeout(job_id)
        time.sleep(min(voice.get("poll_interval", 2), max(0, deadline - time.monotonic())))
        status = observe("status", payload)
    if status["state"] != "succeeded":
        raise RuntimeError(f"Remote voice job {job_id}: {status.get('error', status['state'])}")
    result = status["result"]
    if result["job_id"] != job_id or result["settings"] != settings or len(result["audio"]) != len(texts):
        raise ValueError("Remote result identity/count mismatch")
    validate_audio_identity(spec, result)
    destination = Path(root).resolve() / "media/voice" / job_id
    destination.mkdir(parents=True, exist_ok=True)
    for index, (item, text) in enumerate(zip(result["audio"], texts)):
        if (item["slide_id"], item["beat_id"], item["text_hash"], item["narration_hash"]) != (
                text["slide_id"], text["beat_id"], content_hash(text["text"]), content_hash(text["narration"])):
            raise ValueError("Remote result text mismatch")
        if item["sample_count"] != item["samples"] or item["spoken_text"] != text["text"] or item["narration"] != text["narration"]:
            raise ValueError("Remote result spoken text/sample count mismatch")
        name = f"{index:04d}.wav"
        if item["file"] != name:
            raise ValueError("Unsafe remote audio filename")
        path = destination / name
        expected_metadata = {k: item[k] for k in ("sample_rate", "samples", "duration", "sha256")}
        try:
            local_valid = audio_metadata(path) == expected_metadata
        except (OSError, ValueError):
            local_valid = False
        if not local_valid:
            data = request(voice, "audio", dict(payload, file=name))
            pending = path.with_suffix(".wav.tmp")
            pending.write_bytes(data)
            try:
                if audio_metadata(pending) != expected_metadata:
                    raise ValueError("Audio integrity/metadata mismatch")
                pending.replace(path)
            finally:
                pending.unlink(missing_ok=True)
        item["path"] = str(path)
    (destination / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result

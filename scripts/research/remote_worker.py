"""Standalone remote JSON protocol, persistent jobs and offline CUDA synthesis.

Only `execute` imports the TTS stack. Job directories are immutable reservations:
running/failed jobs are never automatically restarted, even after SSH disconnect.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import wave

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
EXPECTED_WEIGHTS = {
    "model.safetensors": (3833402552, "38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137"),
    "speech_tokenizer/model.safetensors": (682293092, "836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258"),
}


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def create_manifest(root):
    model = root / "models" / MODEL_ID.split("/")[-1]
    files = []
    for path in sorted(model.rglob("*")):
        relative = path.relative_to(model)
        if path.is_file() and not any(part in {".msc", ".mv", ".cache", "._____temp"} for part in relative.parts):
            if path.is_symlink():
                raise ValueError("Model content must not be symlinked")
            files.append({"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": file_hash(path)})
    by_path = {record["path"]: record for record in files}
    for name, (size, checksum) in EXPECTED_WEIGHTS.items():
        record = by_path.get(name)
        if not record or (record["bytes"], record["sha256"]) != (size, checksum):
            raise ValueError(f"Model weight integrity mismatch: {name}")
    metadata = {}
    for name in (".mv", ".msc"):
        path = model / name
        if path.is_file():
            try:
                metadata[name] = json.loads(path.read_text())
            except (UnicodeError, ValueError):
                metadata[name] = {"bytes": path.stat().st_size, "sha256": file_hash(path)}
    manifest = {"model_id": MODEL_ID, "source": "modelscope", "model_path": str(model),
                "requested_revision": "master", "upstream_revision": None,
                "revision_note": "No immutable ModelScope revision established; identity is exact downloaded content, not a Hugging Face commit.",
                "modelscope_metadata": metadata, "files": files,
                "identity": "sha256:" + digest({"model_id": MODEL_ID, "files": files})}
    atomic_json(root / "model-manifest.json", manifest)
    return manifest


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, allow_nan=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def require_pcm_signal(payload, sample_width=2):
    """Reject exact digital silence only; no subjective loudness threshold."""
    zero = 128 if sample_width == 1 else 0
    if not any(byte != zero for byte in payload):
        raise ValueError("narration PCM has no signal (digital silence)")


def audio_metadata(path):
    try:
        data = Path(path).read_bytes()
        with wave.open(str(path), "rb") as audio:
            samples, rate = audio.getnframes(), audio.getframerate()
            expected = samples * audio.getnchannels() * audio.getsampwidth()
            if samples <= 0 or rate <= 0 or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError("Expected nonempty mono PCM16 WAV")
            payload = audio.readframes(samples)
            if len(payload) != expected:
                raise ValueError("Truncated WAV")
            require_pcm_signal(payload)
        return {"sample_rate": rate, "samples": samples, "duration": samples / rate,
                "sha256": hashlib.sha256(data).hexdigest()}
    except (wave.Error, EOFError) as error:
        raise ValueError("Invalid WAV") from error


def scoped_environment(root):
    paths = {"TMPDIR": "tmp", "TMP": "tmp", "TEMP": "tmp", "PIP_CACHE_DIR": "cache/pip",
             "XDG_CACHE_HOME": "cache/xdg", "HF_HOME": "cache/huggingface",
             "HF_HUB_CACHE": "cache/huggingface/hub", "HF_XET_CACHE": "cache/huggingface/xet",
             "HF_ASSETS_CACHE": "cache/huggingface/assets", "MODELSCOPE_CACHE": "cache/modelscope",
             "MODELSCOPE_HOME": "cache/modelscope-config", "TORCH_HOME": "cache/torch",
             "NUMBA_CACHE_DIR": "cache/numba", "PYTHONPYCACHEPREFIX": "cache/pycache",
             "CUDA_CACHE_PATH": "cache/cuda", "TRITON_CACHE_DIR": "cache/triton",
             "TORCHINDUCTOR_CACHE_DIR": "cache/inductor"}
    environment = os.environ.copy()
    for variable, suffix in paths.items():
        path = root / suffix
        path.mkdir(parents=True, exist_ok=True)
        environment[variable] = str(path)
    environment.update(HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    return environment


def launch_job(root, job_id):
    directory = root / "jobs" / job_id
    with (directory / "worker.log").open("ab") as log:
        subprocess.Popen([str(root / "venv/bin/python"), str(root / "remote_worker.py"),
                          "--root", str(root), "--action", "execute", "--job-id", job_id],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                         env=scoped_environment(root), cwd=root)


def status(root, job_id):
    directory = root / "jobs" / job_id
    if not directory.exists():
        return {"job_id": job_id, "state": "missing"}
    status_file = directory / "status.json"
    state = json.loads(status_file.read_text()) if status_file.exists() else {"job_id": job_id, "state": "queued"}
    if state["state"] == "succeeded":
        state["result"] = json.loads((directory / "result.json").read_text())
    return state


def dispatch(root, action, payload):
    if action == "manifest":
        return create_manifest(root)
    if action == "identity":
        return json.loads((root / "model-manifest.json").read_text())
    job_id = payload.get("job_id", "")
    if not re.fullmatch(r"[a-f0-9]{64}", job_id):
        raise ValueError("Invalid job ID")
    directory = root / "jobs" / job_id
    if action == "status":
        return status(root, job_id)
    if action == "submit":
        expected = digest({"protocol": 1, "texts": payload["texts"], "settings": payload["settings"]})
        if expected != job_id:
            raise ValueError("Job content hash mismatch")
        directory.parent.mkdir(exist_ok=True)
        try:
            directory.mkdir()
        except FileExistsError:
            return status(root, job_id)
        atomic_json(directory / "job.json", payload)
        atomic_json(directory / "status.json", {"job_id": job_id, "state": "running"})
        try:
            launch_job(root, job_id)
        except Exception as error:
            atomic_json(directory / "status.json", {"job_id": job_id, "state": "failed", "error": str(error)})
        return status(root, job_id)
    if action == "audio":
        if status(root, job_id)["state"] != "succeeded" or not re.fullmatch(r"\d{4}\.wav", payload.get("file", "")):
            raise ValueError("Audio is not available")
        return (directory / payload["file"]).read_bytes()
    raise ValueError("Unknown action")


def generate_offline(texts, settings, output):
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    torch.manual_seed(settings["seed"])
    torch.cuda.reset_peak_memory_stats()
    start = time.monotonic()
    model = Qwen3TTSModel.from_pretrained(settings["model_path"], device_map="cuda:0",
                                        dtype=torch.bfloat16, attn_implementation="sdpa", local_files_only=True)
    loaded = time.monotonic()
    timings = []
    for index, text in enumerate(texts):
        began = time.monotonic()
        # A cue's stochastic output must not depend on preceding cache misses.
        torch.manual_seed(settings["seed"])
        wavs, rate = model.generate_custom_voice(text=text["text"], language=settings["language"],
                                                speaker=settings["speaker"], instruct=settings["instruct"],
                                                **settings["generation"])
        sf.write(str(output / f"{index:04d}.wav"), wavs[0], rate, subtype="PCM_16")
        torch.cuda.synchronize()
        timings.append(time.monotonic() - began)
    return {"load_seconds": loaded - start, "generation_seconds": sum(timings),
            "cue_seconds": timings, "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "offline": True}


def materialize_audio(root, job, output, generator):
    """Reuse validated semantic cues across jobs; load a model only for misses.

    A task-local advisory lock serializes cache population and GPU inference.
    IDs, original narration, physical model path and GPU choice do not change
    the spoken waveform identity; actual model content and voice settings do.
    """
    cache = root / "cache/audio"
    cache.mkdir(parents=True, exist_ok=True)
    settings = {key: value for key, value in job["settings"].items() if key not in {"gpu", "model_path"}}
    keys = [digest({"protocol": 1, "text": text["text"], "settings": settings}) for text in job["texts"]]
    with (cache.parent / "audio.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        missing, existing = {}, set()
        for key, text in zip(keys, job["texts"]):
            try:
                metadata = json.loads((cache / f"{key}.json").read_text())
                valid = metadata == {"key": key, **audio_metadata(cache / f"{key}.wav")}
            except (OSError, ValueError, KeyError):
                valid = False
            if valid:
                existing.add(key)
            else:
                missing[key] = text
        metrics = {"load_seconds": 0.0, "generation_seconds": 0.0, "cue_seconds": [], "offline": True}
        if missing:
            pending = output / "pending"
            pending.mkdir(exist_ok=True)
            metrics = generator(list(missing.values()), job["settings"], pending)
            for index, key in enumerate(missing):
                source = pending / f"{index:04d}.wav"
                metadata = {"key": key, **audio_metadata(source)}
                temporary = cache / f"{key}.wav.tmp"
                shutil.copyfile(source, temporary)
                temporary.replace(cache / f"{key}.wav")
                atomic_json(cache / f"{key}.json", metadata)
        for index, key in enumerate(keys):
            shutil.copyfile(cache / f"{key}.wav", output / f"{index:04d}.wav")
        metrics.update(cache_hits=len(keys) - len(missing), generated_cues=len(missing))
    return metrics, keys, existing


def process_job(root, job_id, generator=None):
    started = time.monotonic()
    directory = root / "jobs" / job_id
    try:
        job = json.loads((directory / "job.json").read_text())
        settings = job["settings"]
        os.environ.update(scoped_environment(root))
        os.environ["CUDA_VISIBLE_DEVICES"] = str(settings.get("gpu", 0))
        if generator is None:
            identity = create_manifest(root)
            if identity["identity"] != settings["revision"] or identity["model_path"] != settings["model_path"]:
                raise ValueError("Remote model identity changed")
            model = Path(settings["model_path"]).resolve()
            if not model.is_relative_to((root / "models").resolve()) or not model.is_dir():
                raise ValueError("Model must be an installed task-local directory")
        metrics, keys, existing = materialize_audio(root, job, directory, generator or generate_offline)
        audio = []
        for index, text in enumerate(job["texts"]):
            name = f"{index:04d}.wav"
            audio.append({"slide_id": text["slide_id"], "beat_id": text["beat_id"], "file": name,
                          "cache_key": keys[index], "cache_hit": keys[index] in existing,
                          "spoken_text": text["text"], "narration": text.get("narration", text["text"]),
                          "text_hash": digest(text["text"]), "narration_hash": digest(text.get("narration", text["text"])),
                          **audio_metadata(directory / name)})
            audio[-1]["sample_count"] = audio[-1]["samples"]
        metrics["job_seconds"] = time.monotonic() - started
        result = {"job_id": job_id, "settings": settings, "audio": audio, "metrics": metrics}
        atomic_json(directory / "result.json", result)
        atomic_json(directory / "status.json", {"job_id": job_id, "state": "succeeded"})
    except Exception as error:
        traceback.print_exc()
        atomic_json(directory / "status.json", {"job_id": job_id, "state": "failed", "error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--action", required=True, choices=["manifest", "identity", "status", "submit", "audio", "execute"])
    parser.add_argument("--job-id")
    args = parser.parse_args()
    if args.action == "execute":
        if not re.fullmatch(r"[a-f0-9]{64}", args.job_id or ""):
            raise ValueError("Invalid job ID")
        process_job(args.root, args.job_id)
    else:
        result = dispatch(args.root, args.action, json.load(sys.stdin))
        if isinstance(result, bytes):
            sys.stdout.buffer.write(result)
        else:
            print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

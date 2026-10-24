"""SSH boundary doubles; real worker state machine, WAVs and result validation."""
import copy
import hashlib
import importlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def api(name="voice"):
    try:
        return importlib.import_module("research." + name)
    except ModuleNotFoundError:
        pytest.fail("remote voice contract has not been implemented")


def wav(path, samples=240):
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(b"\x01\x00" * samples)


def test_worker_rejects_valid_header_digital_silence(tmp_path):
    path = tmp_path / "silent.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(bytes(48000))
    with pytest.raises(ValueError, match="signal|silent"):
        api("remote_worker").audio_metadata(path)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    voice, worker = api(), api("remote_worker")
    root = tmp_path / "remote 'quoted; space"
    root.mkdir()
    model = root / "models/model"
    model.mkdir(parents=True)
    (root / "model-manifest.json").write_text(json.dumps({
        "model_id": "Qwen/test", "model_path": str(model),
        "identity": "sha256:" + "a" * 64, "source": "modelscope", "upstream_revision": None,
    }))
    starts, calls = [], []
    monkeypatch.setattr(worker, "launch_job", lambda root, job_id: starts.append(job_id))

    def transport(args, **kwargs):
        assert args[:5] == ["ssh", "-o", "BatchMode=yes", "--", "tts-host"]
        command = shlex.split(args[5])
        calls.append(command)
        if command[0] == "python3" and command[1] == "-c":
            # Deployment is the only permitted outgoing script write.
            assert str(root) in command
            return subprocess.CompletedProcess(args, 0, b"", b"")
        assert command[0] == str(root / "venv/bin/python")
        assert command[1] == str(root / "remote_worker.py")
        action = command[command.index("--action") + 1]
        payload = json.loads(kwargs.get("input") or b"{}")
        result = worker.dispatch(root, action, payload)
        raw = result if isinstance(result, bytes) else json.dumps(result).encode()
        return subprocess.CompletedProcess(args, 0, raw, b"")

    monkeypatch.setattr(voice.subprocess, "run", transport)
    spec = {"voice": {"backend": "ssh", "host": "tts-host", "remote_root": str(root),
                      "model": "Qwen/test", "speaker": "Uncle_Fu", "observation_timeout": 0},
            "slides": [{"id": "s01", "beats": [{"id": "b1", "narration": "CUDA 加速，2026 年。"}]}]}
    return voice, worker, root, spec, starts, calls


def finish(remote, samples=240):
    voice, worker, root, spec, starts, calls = remote
    def generate(texts, settings, output):
        for index, text in enumerate(texts):
            wav(output / f"{index:04d}.wav", samples)
        return {"load_seconds": 0.1, "generation_seconds": 0.2}
    worker.process_job(root, starts[-1], generate)


def test_observation_timeout_resumes_same_job_without_resubmit(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout) as error:
        voice.synthesize_remote(spec, tmp_path / "project")
    assert len(starts) == 1
    finish(remote)
    result = voice.synthesize_remote(spec, tmp_path / "project")
    assert result["job_id"] == error.value.job_id == starts[0]
    assert len(starts) == 1
    item = result["audio"][0]
    assert (item["slide_id"], item["beat_id"], item["sample_rate"], item["samples"], item["duration"]) == ("s01", "b1", 24000, 240, 0.01)
    assert Path(item["path"]).is_file()
    assert item["sample_count"] == 240
    assert item["spoken_text"] == item["narration"] == "CUDA 加速，2026 年。"
    assert result["metrics"]["job_seconds"] > 0


def test_successful_job_is_cached_and_never_restarted(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path / "project")
    finish(remote)
    first = voice.synthesize_remote(spec, tmp_path / "project")
    assert voice.synthesize_remote(spec, tmp_path / "project") == first
    assert len(starts) == 1


@pytest.mark.parametrize("corruption", ["garbage", "empty", "truncated"])
def test_corrupted_local_download_is_repaired_from_successful_remote_job(remote, tmp_path, corruption):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path / "project")
    finish(remote)
    first = voice.synthesize_remote(spec, tmp_path / "project")
    path = Path(first["audio"][0]["path"])
    original = path.read_bytes()
    damaged = {"garbage": b"not a WAV", "empty": b"", "truncated": original[:50]}[corruption]
    path.write_bytes(damaged)
    repaired = voice.synthesize_remote(spec, tmp_path / "project")
    assert repaired == first
    assert path.read_bytes() == original
    assert len(starts) == 1
    assert not path.with_suffix(".wav.tmp").exists()


@pytest.mark.parametrize("kind", ["empty", "garbage", "truncated", "hash", "metadata", "escape"])
def test_invalid_remote_audio_is_rejected(remote, tmp_path, kind):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path / "project")
    finish(remote, 0 if kind == "empty" else 240)
    job = root / "jobs" / starts[0]
    result_path = job / "result.json"
    if not result_path.exists():
        with pytest.raises(RuntimeError):
            voice.synthesize_remote(spec, tmp_path / "project")
        return
    result = json.loads(result_path.read_text())
    audio = job / "0000.wav"
    if kind == "garbage":
        audio.write_bytes(b"not a wave")
        result["audio"][0]["sha256"] = hashlib.sha256(audio.read_bytes()).hexdigest()
    elif kind == "truncated":
        audio.write_bytes(audio.read_bytes()[:50])
        result["audio"][0]["sha256"] = hashlib.sha256(audio.read_bytes()).hexdigest()
    elif kind == "hash":
        result["audio"][0]["sha256"] = "0" * 64
    elif kind == "metadata":
        result["audio"][0]["samples"] += 1
    elif kind == "escape":
        result["audio"][0]["file"] = "../../escape.wav"
    result_path.write_text(json.dumps(result))
    with pytest.raises((RuntimeError, ValueError)):
        voice.synthesize_remote(spec, tmp_path / "project")


def test_failed_job_stays_failed_and_does_not_restart(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path)
    def broken(*args):
        raise ValueError("GPU unavailable")
    worker.process_job(root, starts[0], broken)
    with pytest.raises(RuntimeError, match="GPU unavailable"):
        voice.synthesize_remote(spec, tmp_path)
    assert len(starts) == 1


def test_ssh_parameters_are_quoted_and_no_local_model_import(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    original = __import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith(("qwen_tts", "torch", "modelscope", "huggingface_hub"))
        return original(name, *args, **kwargs)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("builtins.__import__", guarded)
    try:
        with pytest.raises(voice.VoiceObservationTimeout):
            voice.synthesize_remote(spec, tmp_path)
    finally:
        monkeypatch.undo()
    assert all(command[command.index("--root") + 1] == str(root) for command in calls if "--root" in command)


@pytest.mark.parametrize("field,value", [("speaker", "other"), ("revision", "other"),
    ("generation", {"temperature": 0.5}), ("pronunciation", {"CUDA": "库达"})])
def test_cache_identity_changes_with_spoken_configuration(field, value):
    voice = api()
    texts = [{"slide_id": "s1", "beat_id": "b1", "text": "CUDA 2026"}]
    settings = {"model": "Qwen/test", "revision": "content-1", "speaker": "Uncle_Fu"}
    changed = dict(settings, **{field: value})
    assert voice.voice_job_id(texts, settings) != voice.voice_job_id(texts, changed)
    assert voice.voice_job_id(texts, settings) != voice.voice_job_id([dict(texts[0], text="CUDA 2027")], settings)
    assert voice.voice_job_id(texts, settings) == voice.voice_job_id(copy.deepcopy(texts), dict(reversed(list(settings.items()))))


def test_pronunciation_final_spoken_copy_and_hash_are_preserved(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    spec["voice"]["pronunciation"] = {"CUDA": "库达"}
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path)
    job = json.loads((root / "jobs" / starts[0] / "job.json").read_text())
    assert job["texts"][0]["text"] == "库达 加速，2026 年。"
    assert job["texts"][0]["narration"] == "CUDA 加速，2026 年。"
    finish(remote)
    item = voice.synthesize_remote(spec, tmp_path)["audio"][0]
    assert item["text_hash"] != item["narration_hash"]


def test_worker_submit_is_atomic_and_idempotent(remote):
    voice, worker, root, spec, starts, calls = remote
    job = {"texts": [{"slide_id": "s", "beat_id": "b", "text": "测试"}], "settings": {"speaker": "Uncle_Fu"}}
    job["job_id"] = voice.voice_job_id(job["texts"], job["settings"])
    assert worker.dispatch(root, "submit", job)["state"] == "running"
    assert worker.dispatch(root, "submit", job)["state"] == "running"
    assert starts == [job["job_id"]]
    assert not list((root / "jobs" / job["job_id"]).glob("*.tmp"))


@pytest.mark.parametrize("field,value", [("host", "-oProxyCommand=bad"), ("remote_root", "/"),
                                        ("backend", "local"), ("remote_root", "/home/alice")])
def test_invalid_transport_settings_never_execute_ssh(remote, tmp_path, field, value):
    voice, worker, root, spec, starts, calls = remote
    spec["voice"][field] = value
    with pytest.raises(ValueError):
        voice.synthesize_remote(spec, tmp_path)
    assert calls == []


def test_manifest_identity_tracks_all_model_content_and_verifies_weights(tmp_path, monkeypatch):
    worker = api("remote_worker")
    model = tmp_path / "models/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    (model / "speech_tokenizer").mkdir(parents=True)
    (model / "model.safetensors").write_bytes(b"main")
    (model / "speech_tokenizer/model.safetensors").write_bytes(b"tokenizer")
    (model / "config.json").write_text('{"model_type":"qwen"}')
    (model / ".mv").write_text('{"Revision":"master","CreatedTime":1}')
    monkeypatch.setattr(worker, "EXPECTED_WEIGHTS", {
        "model.safetensors": (4, hashlib.sha256(b"main").hexdigest()),
        "speech_tokenizer/model.safetensors": (9, hashlib.sha256(b"tokenizer").hexdigest())})
    first = worker.create_manifest(tmp_path)
    assert first["upstream_revision"] is None
    assert first["modelscope_metadata"][".mv"]["Revision"] == "master"
    assert len(first["files"]) == 3
    (model / "config.json").write_text('{"model_type":"changed"}')
    second = worker.create_manifest(tmp_path)
    assert first["identity"] != second["identity"]
    (model / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="weight"):
        worker.create_manifest(tmp_path)


def test_environment_scopes_all_caches_without_changing_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/unchanged")
    environment = api("remote_worker").scoped_environment(tmp_path)
    for key in ["MODELSCOPE_HOME", "MODELSCOPE_CACHE", "HF_HOME", "PIP_CACHE_DIR", "TMPDIR", "TMP", "TEMP",
                "XDG_CACHE_HOME", "TORCH_HOME", "PYTHONPYCACHEPREFIX", "CUDA_CACHE_PATH", "NUMBA_CACHE_DIR"]:
        assert Path(environment[key]).is_relative_to(tmp_path)
        assert Path(environment[key]).is_dir()
    assert environment["HOME"] == "/unchanged"
    assert environment["HF_HUB_OFFLINE"] == environment["TRANSFORMERS_OFFLINE"] == "1"


def test_worker_rejects_content_job_id_mismatch(remote):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(ValueError, match="hash"):
        worker.dispatch(root, "submit", {"job_id": "a" * 64, "texts": [], "settings": {}})
    assert starts == []


def test_lost_ssh_submit_response_still_reports_recoverable_job_id(remote, tmp_path, monkeypatch):
    voice, worker, root, spec, starts, calls = remote
    transport = voice.subprocess.run
    def lose_response(args, **kwargs):
        result = transport(args, **kwargs)
        if "submit" in shlex.split(args[5]):
            raise subprocess.TimeoutExpired(args, 30)
        return result
    monkeypatch.setattr(voice.subprocess, "run", lose_response)
    with pytest.raises(voice.VoiceObservationTimeout) as error:
        voice.synthesize_remote(spec, tmp_path)
    assert error.value.job_id == starts[0]
    finish(remote)
    assert voice.synthesize_remote(spec, tmp_path)["job_id"] == starts[0]
    assert len(starts) == 1


@pytest.fixture
def cue_jobs(remote):
    voice, worker, root, spec, starts, calls = remote
    generated = []
    def generate(texts, settings, output):
        generated.append([text["text"] for text in texts])
        for index, text in enumerate(texts):
            wav(output / f"{index:04d}.wav", 240 + len(text["text"]))
        return {"load_seconds": 0.1, "generation_seconds": 0.2}
    def run(texts, settings=None, narrations=None):
        settings = settings or {"model": "Qwen/test", "revision": "sha256:first", "speaker": "Uncle_Fu",
                                "pronunciation": {}, "generation": {"do_sample": False}, "seed": 0}
        items = [{"slide_id": "s", "beat_id": f"b{i}", "text": text,
                  "narration": narrations[i] if narrations else text} for i, text in enumerate(texts)]
        job_id = voice.voice_job_id(items, settings)
        worker.dispatch(root, "submit", {"job_id": job_id, "texts": items, "settings": settings})
        worker.process_job(root, job_id, generate)
        result = worker.dispatch(root, "status", {"job_id": job_id})
        assert result["state"] == "succeeded"
        return result["result"]
    return run, generated, root


def test_editing_one_beat_reuses_other_verified_audio(cue_jobs):
    run, generated, root = cue_jobs
    first = run(["第一句", "第二句", "第三句"])
    second = run(["第一句", "第二句改写", "第三句"])
    assert generated == [["第一句", "第二句", "第三句"], ["第二句改写"]]
    assert second["metrics"]["cache_hits"] == 2
    assert second["metrics"]["generated_cues"] == 1
    assert [item["beat_id"] for item in second["audio"]] == ["b0", "b1", "b2"]
    assert second["audio"][0]["sha256"] == first["audio"][0]["sha256"]
    assert second["audio"][2]["sha256"] == first["audio"][2]["sha256"]


def test_cue_cache_ignores_position_ids_and_preserves_current_narration(cue_jobs):
    run, generated, root = cue_jobs
    first = run(["第一句", "第二句", "第三句"])
    second = run(["第三句", "第一句"], narrations=["第三句原始写法", "第一句"])
    assert generated == [["第一句", "第二句", "第三句"]]
    assert second["audio"][0]["beat_id"] == "b0"
    assert second["audio"][0]["sha256"] == first["audio"][2]["sha256"]
    assert second["audio"][0]["narration"] == "第三句原始写法"
    assert second["audio"][0]["narration_hash"] != first["audio"][2]["narration_hash"]
    assert second["audio"][0]["text_hash"] == first["audio"][2]["text_hash"]
    assert second["metrics"]["generated_cues"] == 0


@pytest.mark.parametrize("field,value", [("speaker", "other"), ("revision", "sha256:other"),
                                        ("generation", {"do_sample": True}), ("seed", 1),
                                        ("pronunciation", {"术语": "读音"})])
def test_voice_model_generation_and_pronunciation_changes_invalidate_cues(cue_jobs, field, value):
    run, generated, root = cue_jobs
    first = run(["第一句", "第二句", "第三句"])
    settings = dict(first["settings"], **{field: value})
    second = run(["第一句", "第二句", "第三句"], settings)
    assert generated == [["第一句", "第二句", "第三句"], ["第一句", "第二句", "第三句"]]
    assert second["metrics"]["cache_hits"] == 0


def test_corrupt_cue_cache_is_regenerated_not_reused(cue_jobs):
    run, generated, root = cue_jobs
    first = run(["第一句", "第二句", "第三句"])
    cache = root / "cache/audio" / (first["audio"][1]["cache_key"] + ".wav")
    cache.write_bytes(b"bad wav")
    second = run(["第三句", "第二句", "第一句"])
    assert generated == [["第一句", "第二句", "第三句"], ["第二句"]]
    assert second["metrics"]["cache_hits"] == 2


def test_self_consistent_silent_cache_is_regenerated(cue_jobs):
    run, generated, root = cue_jobs
    first = run(["第一句", "第二句"])
    cue = first["audio"][0]
    cache = root / "cache/audio" / (cue["cache_key"] + ".wav")
    with wave.open(str(cache), "wb") as out:
        out.setparams((1, 2, cue["sample_rate"], 0, "NONE", "not compressed"))
        out.writeframes(bytes(cue["sample_count"] * 2))
    cache.with_suffix(".json").write_text(json.dumps({"key": cue["cache_key"],
        "sample_rate": cue["sample_rate"], "samples": cue["sample_count"], "duration": cue["duration"],
        "sha256": hashlib.sha256(cache.read_bytes()).hexdigest()}))
    second = run(["第二句", "第一句"])
    assert generated == [["第一句", "第二句"], ["第一句"]]
    assert second["metrics"]["cache_hits"] == 1


def test_silent_generator_result_cannot_be_published(remote, tmp_path):
    voice, worker, root, spec, starts, calls = remote
    with pytest.raises(voice.VoiceObservationTimeout):
        voice.synthesize_remote(spec, tmp_path / "client")
    def silent(texts, settings, output):
        with wave.open(str(output / "0000.wav"), "wb") as out:
            out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            out.writeframes(bytes(48000))
        return {}
    worker.process_job(root, starts[-1], silent)
    status = worker.status(root, starts[-1])
    assert status["state"] == "failed" and "no signal" in status["error"]
    assert not (root / "jobs" / starts[-1] / "result.json").exists()


def test_each_generated_cue_restarts_its_seed_independent_of_batch_position(tmp_path, monkeypatch):
    worker = api("remote_worker")
    state, observed = [0], []
    def seed(value):
        state[0] = value
    def generate(**kwargs):
        observed.append(state[0])
        state[0] += 1
        return [[0.0]], 24000
    cuda = SimpleNamespace(reset_peak_memory_stats=lambda: None, synchronize=lambda: None,
        max_memory_allocated=lambda: 100, max_memory_reserved=lambda: 200, get_device_name=lambda: "test")
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(manual_seed=seed, cuda=cuda,
        bfloat16="bf16", __version__="test"))
    monkeypatch.setitem(sys.modules, "qwen_tts", SimpleNamespace(Qwen3TTSModel=SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: SimpleNamespace(generate_custom_voice=generate))))
    monkeypatch.setitem(sys.modules, "soundfile", SimpleNamespace(write=lambda path, *args, **kwargs: wav(Path(path))))
    settings = {"seed": 7, "model_path": "/remote/models/model", "language": "Chinese",
                "speaker": "Uncle_Fu", "instruct": "沉稳清晰", "generation": {"do_sample": True}}
    worker.generate_offline([{"text": "第一句"}, {"text": "第二句"}], settings, tmp_path)
    assert observed == [7, 7]

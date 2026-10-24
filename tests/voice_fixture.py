"""Synthetic WAV provenance for tests only; no synthesized speech claim."""
from research.spec import content_hash


def bind_audio(spec, audio):
    voice = spec.setdefault("voice", {"model": "synthetic/test", "speaker": "synthetic"})
    defaults = {"language": "Chinese", "instruct": "用沉稳、清晰的普通话讲解科研内容，语速适中，术语之间自然停顿。",
                "pronunciation": {}, "generation": {"do_sample": False, "max_new_tokens": 2048},
                "seed": 0, "gpu": 0}
    settings = {k: voice.get(k, v) for k, v in defaults.items()}
    settings.update(model=voice["model"], speaker=voice["speaker"],
                    revision="sha256:" + "a" * 64, model_path="/synthetic/no-model")
    audio["settings"] = settings
    texts = [{"slide_id": c["slide_id"], "beat_id": c["beat_id"],
              "text": c["spoken_text"], "narration": c["narration"]} for c in audio["audio"]]
    audio["job_id"] = content_hash({"protocol": 1, "texts": texts, "settings": settings})
    for i, cue in enumerate(audio["audio"]):
        cue["file"] = f"{i:04d}.wav"
        cue["cache_key"] = content_hash({"protocol": 1, "text": cue["spoken_text"],
            "settings": {k: v for k, v in settings.items() if k not in {"gpu", "model_path"}}})
    return audio

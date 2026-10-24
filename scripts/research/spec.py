"""Additive v0.2 research-video contract (v0.1 remains supported).

v0.2 retains project/narrative/slides and evidence-map IDs from v0.1. It adds
render={width:1920,height:1080,fps:60} (missing entries default), an explicit
voice={backend:'ssh',host:<SSH alias>,remote_root:<absolute POSIX directory>,
model:<model ID/revision>,speaker:<voice ID>}, slide.screen_text={key:final copy},
and beat.screen_text=[keys from that slide]. Beat narration is spoken copy;
action is internal. Required outputs are video (.mp4), pptx, speech (.md).
Themes are midnight/paper/slate/custom; custom uses project.theme_custom, a
project-relative YAML file. Paths cannot escape the project, including symlinks.
Recommended remote_root is /srv/manim-tts, not / or a home root.

Extra delivered copy (README, report, etc.) belongs in audience_text, a nested
mapping/list of final strings. All visible labels/captions/subtitles must be
registered in screen_text or the corresponding explicit audience fields.
validate_spec permits work in progress without approval. Release gates call
validate_text_review: text_review.content_hash and both humanizer/humanizer-zh
records {status:'approved',content_hash:<digest>} must match current copy.
These records attest manual review; mechanical audit never creates approvals.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any


def content_hash(value: object) -> str:
    """SHA-256 of canonical UTF-8 JSON (sorted keys, no whitespace, no NaN)."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def render_settings(data: dict) -> dict[str, int]:
    """Return explicit/default render settings without changing the input spec."""
    settings = {"width": 1920, "height": 1080, "fps": 60}
    if isinstance(data.get("render"), dict):
        settings.update({key: data["render"][key] for key in settings if key in data["render"]})
    return settings


def audience_copy(data: dict) -> dict[str, str]:
    """Return path→final audience string, excluding actions, IDs, QA and metadata.

    Includes title, thesis/takeaways, slide section/title/claim/notes and registered
    screen text, labels, legends, captions, subtitles, beat narration, plus all
    audience_text document extras. Nested values retain stable dotted/index paths;
    special mapping keys use JSON-quoted brackets so paths cannot alias each other.
    """
    result: dict[str, str] = {}

    def collect(value: Any, path: str) -> None:
        if isinstance(value, str):
            result[path] = value
        elif isinstance(value, dict):
            for key, child in value.items():
                suffix = f".{key}" if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key) else f"[{json.dumps(key, ensure_ascii=False)}]"
                collect(child, f"{path}{suffix}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect(child, f"{path}[{index}]")

    def fields(value: Any, base: str, names: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for name in names:
                if name in value:
                    collect(value[name], f"{base}.{name}")

    fields(data.get("project"), "project", ("title", "subtitle"))
    fields(data.get("narrative"), "narrative", ("thesis", "takeaways"))
    visible = ("title", "section", "claim", "notes", "screen_text", "body",
               "label", "labels", "legend", "legends", "caption", "captions",
               "subtitle", "subtitles")
    slides = data.get("slides")
    for index, slide in enumerate(slides if isinstance(slides, list) else []):
        base = f"slides[{index}]"
        fields(slide, base, visible)
        if not isinstance(slide, dict) or not isinstance(slide.get("beats"), list):
            continue
        for beat_index, beat in enumerate(slide["beats"]):
            fields(beat, f"{base}.beats[{beat_index}]", ("narration", "caption", "captions", "subtitles"))
    collect(data.get("audience_text"), "audience_text")
    return result


def validate_text_review(data: dict) -> list[str]:
    """Release gate: require both manual review passes for current audience-copy hash.

    No side effects or automatic approval. Call after registering actual final
    document/scene copy, and repeat after any audience-facing text change.
    """
    digest = content_hash(audience_copy(data))
    review = data.get("text_review")
    if not isinstance(review, dict):
        return ["text_review: two versioned manual review records are required"]
    errors = []
    if review.get("content_hash") != digest:
        errors.append("text_review.content_hash: does not match current audience copy")
    for name in ("humanizer", "humanizer-zh"):
        record = review.get(name)
        if not isinstance(record, dict) or record.get("status") != "approved" or record.get("content_hash") != digest:
            errors.append(f"text_review.{name}: approved record for current content_hash is required")
    return errors


def _safe_path(value: Any, root: Path) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value or "\x00" in value:
        return False
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).drive or ".." in path.parts or path == Path("."):
        return False
    try:
        return (root / path).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError):
        return False


def validate_spec(data: dict, root: Path) -> list[str]:
    """Return all validation errors as 'path: message'; verify local source files.

    root is the project directory, not planning/. Does not mutate data, synthesize
    media, connect SSH or require completed manual reviews. v0.1 uses its existing
    validator unchanged; use validate_text_review separately before final export.
    """
    return _validate(data, Path(root), check_paths=True)


def _validate(data: dict, root: Path, *, check_paths: bool) -> list[str]:
    from validate_deck import _validate_deck

    if not isinstance(data, dict):
        return ["spec: must be a mapping"]
    version = str(data.get("schema_version"))
    if version != "0.2":
        return [f"{f.path}: {f.message}" for f in _validate_deck(
            data, deck_path=root / "planning/deck.yaml", check_paths=check_paths)
                if f.severity == "error"]

    errors = [f"{f.path}: {f.message}" for f in _validate_deck(
        data, deck_path=root / "planning/deck.yaml", check_paths=check_paths,
        schema_version="0.2", required_outputs={"video", "pptx", "speech"}) if f.severity == "error"]

    def error(path: str, message: str) -> None:
        errors.append(f"{path}: {message}")

    if "render" in data and not isinstance(data["render"], dict):
        error("render", "must be a mapping")
    settings = render_settings(data)
    for key, value in settings.items():
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            error(f"render.{key}", "must be a positive integer")
    if all(isinstance(settings[k], int) and not isinstance(settings[k], bool) and settings[k] > 0 for k in ("width", "height")):
        if settings["width"] * 9 != settings["height"] * 16:
            error("render", "width and height must have a 16:9 aspect ratio")

    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    theme = project.get("theme")
    if not isinstance(theme, str) or theme not in {"midnight", "paper", "slate", "custom"}:
        error("project.theme", "must be midnight, paper, slate or custom")
    paths = {f"project.source_files[{i}]": p for i, p in enumerate(project.get("source_files", []))} if isinstance(project.get("source_files"), list) else {}
    if project.get("theme") == "custom":
        paths["project.theme_custom"] = project.get("theme_custom")
    outputs = data.get("outputs")
    if isinstance(outputs, dict):
        paths.update({f"outputs.{name}": p for name, p in outputs.items()})
    for path, value in paths.items():
        if not _safe_path(value, root):
            error(path, "must be a project-relative path without traversal or escaping symlinks")
        elif check_paths and path == "project.theme_custom" and not (root / value).is_file():
            error(path, "custom theme file does not exist")

    voice = data.get("voice")
    if not isinstance(voice, dict):
        error("voice", "must be a mapping with SSH backend configuration")
        voice = {}
    if voice.get("backend") != "ssh":
        error("voice.backend", "must be ssh; no local model is loaded")
    host = voice.get("host")
    if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", host):
        error("voice.host", "must be an SSH config alias, not credentials or an address")
    remote = voice.get("remote_root")
    remote_parts = PurePosixPath(remote).parts[1:] if isinstance(remote, str) else ()
    home_root = (remote_parts in {("root",), ("var", "root")}
                 or bool(remote_parts) and remote_parts[0] in {"home", "Users"} and len(remote_parts) <= 2)
    if (not isinstance(remote, str) or not remote.startswith("/") or "\\" in remote
            or "\x00" in remote or ".." in PurePosixPath(remote).parts
            or not remote_parts or home_root):
        error("voice.remote_root", "must be an absolute POSIX directory without traversal; / and home roots are forbidden")
    for field in ("model", "speaker"):
        if not isinstance(voice.get(field), str) or not voice[field].strip():
            error(f"voice.{field}", "must be a non-empty string")

    slides = data.get("slides")
    for index, slide in enumerate(slides if isinstance(slides, list) else []):
        if not isinstance(slide, dict):
            continue
        base = f"slides[{index}]"
        registry = slide.get("screen_text")
        if not isinstance(registry, dict) or not registry:
            error(f"{base}.screen_text", "must be a non-empty text ID to final string mapping")
            registry = {}
        for key, text in registry.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", key) or not isinstance(text, str) or not text.strip():
                error(f"{base}.screen_text.{key}", "requires a stable text ID and non-empty final string")
        beats = slide.get("beats")
        for beat_index, beat in enumerate(beats if isinstance(beats, list) else []):
            if not isinstance(beat, dict):
                continue
            path = f"{base}.beats[{beat_index}].screen_text"
            refs = beat.get("screen_text")
            if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                error(path, "must be a list of per-slide text IDs (empty allowed for visual-only beats)")
            else:
                for ref in refs:
                    if ref not in registry:
                        error(path, f"text ID is not registered: {ref}")

    # Imported here to keep audience_copy usable by audit_text without a cycle.
    from audit_text import audit
    errors.extend(f"{f.path}: {f.label}: {f.excerpt}" for f in audit(data) if f.severity == "error")
    return errors

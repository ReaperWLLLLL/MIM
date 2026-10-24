"""Voice-free preview spec validation and exact authored integer-frame freezing.

The builder checks pure structure only. Call validate_preview_spec with the
project root before executing source files or loading a custom theme. Manual
text approval remains the existing, separate validate_text_review release gate.
No rendering, audio, SSH, or model imports are needed by this module.
"""
from __future__ import annotations

from copy import deepcopy
import keyword
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from .spec import audience_copy, content_hash, _safe_path
from .themes import load_theme


def _require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise ValueError(f"{path}: {message}")


def _mapping(value: object, path: str, required: set[str], optional: set[str] | None = None) -> dict:
    _require(isinstance(value, dict), path, "must be a mapping")
    _require(required <= value.keys(), path, "missing required fields")
    _require(value.keys() <= required | (optional or set()), path, "unknown fields are forbidden")
    return value


def _text(value: object, path: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), path, "must be a non-empty string")


def _id(value: object, path: str) -> None:
    _require(isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value) is not None,
             path, "requires a stable ID")


def _items(value: object, path: str) -> list:
    _require(isinstance(value, list) and bool(value), path, "must be a non-empty list")
    return value


def _positive_int(value: object, path: str) -> None:
    _require(type(value) is int and value > 0, path, "must be a positive integer")


def _relative_path(value: object, path: str, root: Path | None) -> None:
    _text(value, path)
    _require("\\" not in value and "\x00" not in value and not PureWindowsPath(value).drive
             and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
             and PurePosixPath(value) != PurePosixPath("."), path,
             "must be a project-relative path without traversal")
    if root is not None:
        _require(_safe_path(value, root), path, "escaping symlinks are forbidden")
        _require((root / value).is_file(), path, "file does not exist")


def _audience_tree(value: object, path: str) -> None:
    if isinstance(value, str):
        _text(value, path)
    elif isinstance(value, dict):
        for key, child in value.items():
            _text(key, path)
            _audience_tree(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _audience_tree(child, f"{path}[{index}]")
    else:
        raise ValueError(f"{path}: must contain only final strings, mappings or lists")


def _check_spec(spec: dict, root: Path | None = None) -> None:
    _mapping(spec, "spec", {"schema_version", "project", "slides"}, {"audience_text", "text_review"})
    _require(spec["schema_version"] == "research-preview-spec-1", "schema_version", "unsupported preview spec")
    project = _mapping(spec["project"], "project", {"title", "theme", "source_files"}, {"theme_custom"})
    _text(project["title"], "project.title")
    theme = project["theme"]
    _require(isinstance(theme, str) and theme in {"midnight", "paper", "slate", "custom"},
             "project.theme", "must be midnight, paper, slate or custom")
    for index, source in enumerate(_items(project["source_files"], "project.source_files")):
        _relative_path(source, f"project.source_files[{index}]", root)
    if theme == "custom":
        _relative_path(project.get("theme_custom"), "project.theme_custom", root)
        if root is not None:
            from common import load_structured_file
            try:
                load_theme(theme, load_structured_file(root / project["theme_custom"]))
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f"project.theme_custom: {exc}") from exc
    else:
        _require("theme_custom" not in project, "project.theme_custom", "requires theme=custom")
        load_theme(theme)
    slide_ids = set()
    for index, slide in enumerate(_items(spec["slides"], "slides")):
        path = f"slides[{index}]"
        _mapping(slide, path, {"id", "scene_class", "screen_text", "beats"})
        _id(slide["id"], f"{path}.id")
        _require(slide["id"] not in slide_ids, f"{path}.id", "duplicate slide ID")
        slide_ids.add(slide["id"])
        cls = slide["scene_class"]
        _require(isinstance(cls, str) and cls.isidentifier() and not keyword.iskeyword(cls),
                 f"{path}.scene_class", "must be a Python class identifier")
        registry = slide["screen_text"]
        _require(isinstance(registry, dict) and bool(registry), f"{path}.screen_text", "requires a non-empty text registry")
        for key, text in registry.items():
            _id(key, f"{path}.screen_text")
            _text(text, f"{path}.screen_text.{key}")
        ids = set()
        for bi, beat in enumerate(_items(slide["beats"], f"{path}.beats")):
            bp = f"{path}.beats[{bi}]"
            _mapping(beat, bp, {"id", "screen_text"})
            _id(beat["id"], f"{bp}.id")
            _require(beat["id"] not in ids, f"{bp}.id", "duplicate beat ID")
            ids.add(beat["id"])
            refs = beat["screen_text"]
            _require(isinstance(refs, list), f"{bp}.screen_text", "must be a list of registered text IDs")
            for ref in refs:
                _id(ref, f"{bp}.screen_text")
                _require(ref in registry, f"{bp}.screen_text", f"text ID is not registered: {ref}")
    if "audience_text" in spec:
        _audience_tree(spec["audience_text"], "audience_text")
    if "text_review" in spec:
        review = _mapping(spec["text_review"], "text_review", {"content_hash", "humanizer", "humanizer-zh"})
        _text(review["content_hash"], "text_review.content_hash")
        for name in ("humanizer", "humanizer-zh"):
            record = _mapping(review[name], f"text_review.{name}", {"status", "content_hash"})
            for key in record:
                _text(record[key], f"text_review.{name}.{key}")
    # Keep the existing text registry/audit boundary, without generating approvals.
    audience_copy(spec)
    from audit_text import audit
    errors = [f"{f.path}: {f.label}: {f.excerpt}" for f in audit(spec) if f.severity == "error"]
    _require(not errors, "text audit", "; ".join(errors))
    content_hash(spec)  # Reject non-JSON and non-finite metadata at the boundary.


def validate_preview_spec(spec: dict, root: Path) -> list[str]:
    """Return findings for invalid structure, copy, themes and local source paths."""
    try:
        _check_spec(spec, Path(root))
    except (ValueError, TypeError, OSError, RuntimeError, RecursionError) as exc:
        return [str(exc)]
    return []


def build_preview_timeline(spec: dict, authored: dict, fps: int) -> dict:
    """Freeze exact authored frames; no scaling, filesystem access or input mutation."""
    try:
        _positive_int(fps, "fps")
        _check_spec(spec)
        _mapping(authored, "authored", {"schema_version", "mode", "fps", "slides"})
        _require(authored["schema_version"] == "research-authored-timeline-1", "authored.schema_version", "unsupported version")
        _require(authored["mode"] == "silent-preview", "authored.mode", "must be silent-preview")
        _positive_int(authored["fps"], "authored.fps")
        _require(authored["fps"] == fps, "authored.fps", "must match profile fps without scaling")
        source_slides = _items(authored["slides"], "authored.slides")
        _require(len(source_slides) == len(spec["slides"]), "authored.slides", "must match spec slide order exactly")
        slides, cursor = [], 0
        for si, (slide, source) in enumerate(zip(spec["slides"], source_slides)):
            path = f"authored.slides[{si}]"
            _mapping(source, path, {"id", "beats"})
            _require(source["id"] == slide["id"], f"{path}.id", "must match spec slide order exactly")
            sources = _items(source["beats"], f"{path}.beats")
            _require(len(sources) == len(slide["beats"]), f"{path}.beats", "must match spec beat order exactly")
            start, beats = cursor, []
            for bi, (beat, authored_beat) in enumerate(zip(slide["beats"], sources)):
                bp = f"{path}.beats[{bi}]"
                _mapping(authored_beat, bp, {"id", "frames"})
                _require(authored_beat["id"] == beat["id"], f"{bp}.id", "must match spec beat order exactly")
                frames = authored_beat["frames"]
                _positive_int(frames, f"{bp}.frames")
                beats.append({"id": beat["id"], "slide_id": slide["id"], "frames": frames,
                              "start_frame": cursor, "end_frame": cursor + frames,
                              "local_start_frame": cursor - start, "local_end_frame": cursor + frames - start,
                              "duration_seconds": frames / fps})
                cursor += frames
            slides.append({"id": slide["id"], "start_frame": start, "end_frame": cursor,
                           "frames": cursor - start, "beats": beats})
        result = {"schema_version": "research-preview-timeline-1", "mode": "silent-preview", "fps": fps,
                  "spec_hash": content_hash(spec), "authored_hash": content_hash(authored),
                  "authored_identity": deepcopy(authored), "total_frames": cursor,
                  "duration_seconds": cursor / fps, "slides": slides}
        result["timeline_hash"] = content_hash(result)
        return result
    except (KeyError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError(f"invalid preview timeline input: {exc}") from exc


def validate_preview_timeline(timeline: dict, spec: dict, authored: dict, fps: int) -> list[str]:
    """Reconstruct the entire expected payload, including intervals and identities."""
    try:
        expected = build_preview_timeline(spec, authored, fps)
        # Canonical JSON distinguishes integer frames from bools/floats, unlike ==.
        _require(isinstance(timeline, dict) and content_hash(timeline) == content_hash(expected),
                 "timeline", "frozen preview timeline is stale or altered; rebuild from current spec, authored frames and fps")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        return [str(exc)]
    return []

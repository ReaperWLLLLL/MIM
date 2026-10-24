#!/usr/bin/env python3
"""Validate → remote voice → frozen sample timeline → audited silent slide masters.

Export/verify are downstream operations, not implicit side effects of render.
Each CLI path is relative to the caller's working directory. Spec resource paths
remain relative to its project root (planning/deck.yaml → parent of planning).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from fractions import Fraction
import hashlib
import copy
import importlib.metadata
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from common import load_structured_file, project_root_for
from research.spec import content_hash, render_settings, validate_spec, validate_text_review
from research.themes import load_theme
from research.timeline import build_timeline, require_narrated, validate_timeline


def profile_settings(spec, profile):
    if profile == "draft":
        return {"width": 960, "height": 540, "fps": 15}
    if profile != "final":
        raise ValueError("profile must be final or draft")
    return render_settings(spec)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_type,width,height,avg_frame_rate,nb_read_frames", "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    streams = json.loads(result.stdout)["streams"]
    video = [s for s in streams if s["codec_type"] == "video"]
    if len(video) != 1:
        raise ValueError("master must contain exactly one video stream")
    v = video[0]
    return {"width": v["width"], "height": v["height"], "fps": float(Fraction(v["avg_frame_rate"])),
            "observed_frames": int(v["nb_read_frames"]),
            "has_audio": any(s["codec_type"] == "audio" for s in streams)}


def slide_dependency_hash(spec, timing, manifest):
    """Local semantic identity; global offsets, review records and WAV paths do not render.

    Scene code must keep local presentation configuration in its slide spec.
    Common source/runtime changes conservatively invalidate every slide. This is
    not arbitrary-Python dependency inference; external reads need explicit
    project inputs or a full render.
    """
    index, slide = next((i, s) for i, s in enumerate(spec["slides"]) if s["id"] == timing["id"])
    beats = [{k: v for k, v in b.items() if k not in {"path", "start_frame", "end_frame"}}
             for b in timing["beats"]]
    shared = {k: v for k, v in spec.items() if k not in {"slides", "text_review"}}
    # The index is part of native scene naming and output directory identity.
    # Reordering must invalidate reuse before another scene overwrites that path.
    return content_hash({"slide": slide, "scene_index": index, "shared": shared, "beats": beats,
                         **{k: manifest[k] for k in ("settings", "theme", "theme_input", "font", "source", "source_files", "runtime")}})


def render_project(spec, audio, timeline, *, source, out, profile, theme_name=None, theme_file=None, font_file=None, root=None, slides=None, input_paths=()):
    """Render no-cache silent masters; publish manifest only with actual probe evidence.

    One native Manim Slides scene per logical slide retains poster/notes conversion.
    Consumer contract is research-render-1; all artifact paths are absolute. Scene
    class names in spec refer to subclasses in source. No local TTS is performed.
    """
    settings = profile_settings(spec, profile)
    errors = validate_timeline(timeline, spec, audio, settings["fps"])
    if errors:
        raise ValueError("; ".join(errors))
    return _render_validated_project(spec, timeline, source=source, out=out, settings=settings,
        profile=profile, mode="narrated", theme_name=theme_name, theme_file=theme_file,
        font_file=font_file, root=root, slides=slides, input_paths=input_paths)


def _fresh_preview_path(out):
    """Lexical ancestor checks precede resolve/mkdir; existing files include hardlinks."""
    path = Path(out).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError("silent-preview output and ancestors must not be symlinks")
    if path.exists():
        raise ValueError("silent-preview requires a fresh, dedicated output directory")
    return path


@contextmanager
def _preview_imports(source, sources):
    """Only preview-local Python executes from the exact hashed byte snapshots.

    Timestamp/size pyc checks do not establish content identity. A scoped finder
    bypasses those caches for this source inventory and restores prior sibling
    modules afterward; narrated imports and third-party loaders are unchanged.
    """
    names = set()
    for path in sources:
        relative = path.relative_to(source.parent).with_suffix("")
        parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
        # Namespace parents have no __file__. Inventory every package ancestor
        # so prior parents are isolated/restored and new parents are removed.
        names.update(".".join(parts[:end]) for end in range(1, len(parts) + 1))
    def local(name, module):
        return (any(name == key or name.startswith(key + ".") for key in names)
                or (getattr(module, "__file__", None)
                    and Path(module.__file__).resolve() in sources))
    previous = {name: module for name, module in list(sys.modules.items()) if local(name, module)}
    class SnapshotLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            return compile(sources[Path(self.path).resolve()], self.path, "exec")
    class SourceFinder:
        def find_spec(self, fullname, path=None, target=None):
            found = importlib.machinery.PathFinder.find_spec(fullname, path)
            if found and found.origin and Path(found.origin).resolve() in sources:
                found.loader = SnapshotLoader(fullname, found.origin)
                return found
            return None
    finder = SourceFinder()
    for name in previous:
        sys.modules.pop(name, None)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for name, module in list(sys.modules.items()):
            if local(name, module):
                sys.modules.pop(name, None)
        sys.modules.update(previous)


def render_silent_preview(spec, authored, *, source, out, profile="draft", theme_name=None,
                          theme_file=None, font_file=None, root=None, input_paths=()):
    """Render authored frames only; no voice generation, audio or release side effects."""
    from research.preview_timeline import build_preview_timeline, validate_preview_spec
    root = Path(root) if root is not None else Path(source).resolve().parent.parent
    errors = validate_preview_spec(spec, root) + validate_text_review(spec)
    if errors:
        raise ValueError("; ".join(errors))
    settings = profile_settings(spec, profile)
    timeline = build_preview_timeline(spec, authored, settings["fps"])
    return _render_validated_project(spec, timeline, source=source, out=out, settings=settings,
        profile=profile, mode="silent-preview", theme_name=theme_name, theme_file=theme_file,
        font_file=font_file, root=root, input_paths=input_paths)


def _render_validated_project(spec, timeline, *, source, out, settings, profile, mode,
                              theme_name=None, theme_file=None, font_file=None, root=None,
                              slides=None, input_paths=()):
    """One audited rendering kernel; public wrappers validate their separate contracts."""
    if mode not in {"narrated", "silent-preview"}:
        raise ValueError("unsupported render mode")
    preview = mode == "silent-preview"
    if preview:
        from research.preview_timeline import validate_preview_spec, validate_preview_timeline
        errors = validate_preview_spec(spec, root) + validate_text_review(spec)
        errors += validate_preview_timeline(timeline, spec, timeline.get("authored_identity"), settings["fps"])
        if errors:
            raise ValueError("; ".join(errors))
        if slides is not None:
            raise ValueError("silent-preview does not accept partial --slides selection")
        out = _fresh_preview_path(out)
    else:
        require_narrated(spec, timeline)
        if timeline.get("schema_version") != "research-timeline-1":
            raise ValueError("narrated workflow requires research-timeline-1")
    from manim import __version__ as manim_version, tempconfig
    from research.media import _video
    from research.scene import ResearchScene, ensure_font
    source, out = Path(source).resolve(), Path(out).resolve()
    name = theme_name or spec["project"]["theme"]
    custom = theme_file
    if not custom and name == "custom":
        custom = Path(root) / spec["project"]["theme_custom"]
    theme = load_theme(name, load_structured_file(Path(custom)) if custom else None)
    theme_input = {"name": name, "file": None}
    if custom:
        path = Path(custom).absolute()
        theme_input["file"] = {"path": str(path), "resolved_path": str(path.resolve()), "sha256": _sha(path)}
    font = ensure_font(font_file)
    preview_sources = {p: p.read_bytes() for p in sorted(source.parent.rglob("*.py"))} if preview else {}
    # Identity and effective-theme/font validation precede the exclusive mkdir.
    manifest = {"schema_version": "research-render-1", "ok": False, "profile": profile,
                "project_root": str(Path(root).resolve()) if root else None,
                "input_paths": [str(Path(p).absolute()) for p in input_paths],
                "settings": settings, "theme": theme, "theme_input": theme_input, "font": font,
                "spec_hash": timeline["spec_hash"], "timeline_hash": timeline["timeline_hash"],
                "source": {"path": str(source), "sha256": _sha(source)},
                "source_files": {str(p): _sha(p) for p in sorted(source.parent.rglob("*.py"))},
                "runtime": {"manim": manim_version, "python": sys.version,
                    "audit_sources": {p.name: _sha(p) for p in Path(__file__).parent.joinpath("research").glob("*.py")},
                    "build_source": _sha(Path(__file__)),
                    "packages": {name: importlib.metadata.version(name) for name in ("manim-slides", "numpy", "Pillow", "manimpango", "pycairo", "av")},
                    "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0],
                    "caching": False}, "slides": []}
    if preview:
        manifest.update(schema_version="research-preview-render-1", mode=mode,
                        authored_hash=timeline["authored_hash"],
                        input_files=[{"path": str(Path(p).absolute()), "sha256": _sha(p)} for p in input_paths])
        manifest["source"]["sha256"] = hashlib.sha256(preview_sources[source]).hexdigest()
        manifest["source_files"] = {str(p): hashlib.sha256(data).hexdigest() for p, data in preview_sources.items()}
    out.mkdir(parents=True, exist_ok=not preview)
    if preview:
        for key, filename, value in (("spec", "spec.json", spec),
                ("authored_timeline", "authored-timeline.json", timeline["authored_identity"]),
                ("timeline", "preview-timeline.json", timeline)):
            path = out / filename
            _write(path, value)
            manifest[key] = {"path": str(path), "sha256": _sha(path)}
    manifest_path = out / "render-manifest.json"
    selected = set(slides) if slides is not None else {s["id"] for s in spec["slides"]}
    known = {s["id"] for s in spec["slides"]}
    if not selected or not selected <= known:
        raise ValueError("--slides must contain known, nonempty slide IDs")
    timings = {s["id"]: s for s in timeline["slides"]}
    dependencies = {sid: slide_dependency_hash(spec, timings[sid], manifest) for sid in known}
    retained = {}
    if selected != known:
        from research.media import validate_render_slide
        try:
            previous = json.loads(manifest_path.read_text())
            require_narrated(spec, previous)
            if previous.get("schema_version") != "research-render-1":
                raise ValueError("narrated workflow requires research-render-1")
            if not previous["ok"]:
                raise ValueError("previous render did not complete")
            by_id = {s["slide_id"]: s for s in previous["slides"]}
            for sid in known - selected:
                item = copy.deepcopy(by_id[sid])
                if item.get("dependency_hash") != dependencies[sid]:
                    raise ValueError(f"{sid}: stale dependency hash; select this slide or full render")
                validate_render_slide(item, timings[sid], settings)
                retained[sid] = item
        except (OSError, KeyError, ValueError) as exc:
            # Fail before touching selected masters or the successful manifest.
            raise ValueError(f"cannot reuse unselected slide: {exc}") from exc
    _write(manifest_path, manifest)
    imports = _preview_imports(source, preview_sources) if preview else nullcontext()
    try:
        imports.__enter__()
        module_spec = importlib.util.spec_from_file_location("research_user_scenes", source)
        if module_spec is None or module_spec.loader is None:
            raise ValueError("cannot load scene source")
        module = importlib.util.module_from_spec(module_spec)
        sys.path.insert(0, str(source.parent))
        try:
            if preview:
                exec(compile(preview_sources[source], str(source), "exec"), module.__dict__)
            else:
                module_spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        for index, slide in enumerate(spec["slides"]):
            if slide["id"] in retained:
                item = retained[slide["id"]]
                timing = timings[slide["id"]]
                records = [json.loads(line) for line in Path(item["trace"]).read_text().splitlines()]
                mapping = out / f"slide-{index:04d}" / f"frame-map-{timeline['timeline_hash']}.jsonl"
                mapping.write_text("".join(json.dumps({"local_frame": r["local_frame"],
                    "frame": timing["start_frame"] + r["local_frame"], "observed_frame": r["frame"],
                    "source_trace": item["trace"], "source_trace_sha256": item["trace_sha256"]}) + "\n" for r in records))
                item.update({k: timing[k] for k in ("start_frame", "end_frame", "frames")})
                item.update({"reused": True, "frame_mapping": str(mapping), "frame_mapping_sha256": _sha(mapping)})
                manifest["slides"].append(item)
                continue
            cls = getattr(module, slide["scene_class"])
            from research.preview_scene import SilentPreviewScene
            base = SilentPreviewScene if preview else ResearchScene
            if (not isinstance(cls, type) or not issubclass(cls, base)
                    or (not preview and issubclass(cls, SilentPreviewScene))):
                raise ValueError(f"{slide['scene_class']} must inherit {base.__name__} for {mode}")
            # Native Slides JSON uses class names; namespace each logical slide's
            # render class so its metadata and generated files remain separate.
            render_name = f"Research_{index:04d}_{cls.__name__}"
            render_cls = type(render_name, (cls,), {"__module__": module.__name__})
            folder = out / f"slide-{index:04d}"
            with tempconfig({"renderer": "cairo", "pixel_width": settings["width"],
                    "pixel_height": settings["height"], "frame_rate": settings["fps"],
                    "frame_width": 128 / 9, "frame_height": 8,
                    "disable_caching": True, "write_to_movie": True, "save_last_frame": False,
                    "format": "mp4", "media_dir": str(folder / "media"),
                    "output_file": "silent-master", "preview": False, "verbosity": "WARNING",
                    "progress_bar": "none"}):
                scene = render_cls(spec=spec, timeline=timeline, slide_id=slide["id"], theme=theme,
                    audit_dir=folder / "audit", output_folder=folder / "slides")
                scene.skip_reversing = True
                scene.render()
                master = Path(scene.renderer.file_writer.movie_file_path).resolve()
                native = (folder / "slides" / f"{render_name}.json").resolve()
                if not native.is_file():
                    raise ValueError("native Manim Slides metadata was not produced")
                timing = scene.slide_timing
                # Apply the same decoded-frame PTS contract used by publication;
                # average-rate metadata alone cannot prove a regular cadence.
                _video(master, timing, settings)
                observed = _probe(master)
                if (observed["observed_frames"] != timing["frames"]
                        or observed["observed_frames"] != scene._frame_count
                        or any(observed[k] != settings[k] for k in ("width", "height", "fps"))
                        or observed["has_audio"]):
                    raise ValueError(f"master media does not match frozen timing/profile: {observed}")
                trace = (folder / "audit/frames.jsonl").resolve()
                qa = (folder / "audit/qa.json").resolve()
                manifest["slides"].append({"slide_id": slide["id"], "scene_class": render_name,
                    "start_frame": timing["start_frame"], "end_frame": timing["end_frame"],
                    "frames": timing["frames"], "master": str(master), "master_sha256": _sha(master),
                    "trace": str(trace), "trace_sha256": _sha(trace),
                    "qa": str(qa), "qa_sha256": _sha(qa), "reused": False,
                    "dependency_hash": dependencies[slide["id"]],
                    "slides_json": str(native), "slides_json_sha256": _sha(native), **observed})
        manifest["ok"] = True
    except Exception as exc:
        manifest["error"] = str(exc)
        raise
    finally:
        imports.__exit__(None, None, None)
        _write(manifest_path, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "voice", "timeline", "render", "export", "verify", "silent-preview"):
        child = sub.add_parser(command)
        child.add_argument("--spec", required=True, type=Path)
        if command != "validate":
            child.add_argument("--out", required=True, type=Path)
        if command in {"timeline", "render", "export", "verify"}:
            child.add_argument("--audio", required=True, type=Path)
        if command in {"timeline", "render", "export", "verify"}:
            child.add_argument("--profile", choices=["final", "draft"], default="final")
        if command in {"render", "export", "verify"}:
            child.add_argument("--timeline", required=True, type=Path)
        if command == "silent-preview":
            child.add_argument("--authored-timeline", required=True, type=Path)
            child.add_argument("--profile", choices=["draft", "final"], default="draft")
        if command in {"render", "silent-preview"}:
            child.add_argument("--source", required=True, type=Path)
            if command == "render":
                child.add_argument("--slides", help="Comma-separated IDs to rerender; all unselected masters must pass dependency/evidence validation")
            child.add_argument("--theme", choices=["midnight", "paper", "slate", "custom"])
            child.add_argument("--theme-file", type=Path)
            child.add_argument("--font-file", type=Path)
    args = parser.parse_args(argv)
    try:
        spec_path = args.spec.resolve()
        root = project_root_for(spec_path)
        spec = load_structured_file(spec_path)
        if args.command == "silent-preview":
            render_silent_preview(spec, load_structured_file(args.authored_timeline),
                source=args.source, out=args.out, profile=args.profile, theme_name=args.theme,
                theme_file=args.theme_file, font_file=args.font_file, root=root,
                input_paths=(args.spec, args.authored_timeline))
            print(json.dumps({"ok": True, "output": str(args.out.resolve())}, ensure_ascii=False))
            return 0
        require_narrated(spec)
        errors = validate_spec(spec, root)
        if errors:
            raise ValueError("; ".join(errors))
        if str(spec.get("schema_version")) != "0.2":
            raise ValueError("build_research requires schema_version 0.2")
        if args.command in {"render", "export", "verify"}:
            # Check mode/schema before attempting the audio manifest (which may
            # deliberately not exist for a preview).
            timeline = load_structured_file(args.timeline)
            require_narrated(spec, timeline)
            if timeline.get("schema_version") != "research-timeline-1":
                raise ValueError("narrated workflow requires research-timeline-1")
        if args.command == "validate":
            print(json.dumps({"ok": True, "spec": str(spec_path)}, ensure_ascii=False))
            return 0
        if args.command == "voice":
            from research.voice import VoiceObservationTimeout, synthesize_remote
            try:
                result = synthesize_remote(spec, root)
            except VoiceObservationTimeout as exc:
                pending = {"ok": False, "pending": True, "job_id": exc.job_id,
                           "resume": "Repeat the identical voice command to observe the SAME remote job."}
                _write(args.out.with_suffix(".pending.json"), pending)
                print(json.dumps(pending))
                return 2
            _write(args.out, result)
        elif args.command in {"export", "verify"}:
            from research.media import publish_research_outputs, read_json, verify_research_outputs
            timeline = load_structured_file(args.timeline)
            audio = load_structured_file(args.audio)
            errors = validate_timeline(timeline, spec, audio, profile_settings(spec, args.profile)["fps"])
            if errors:
                raise ValueError("; ".join(errors))
            if args.command == "export":
                publish_research_outputs(spec, timeline, audio, args.out, root, args.profile,
                    input_paths=(args.spec, args.audio, args.timeline))
            else:
                exported = read_json(args.out / "export-manifest.json")
                if not exported.get("delivery") or exported["delivery"]["project_root"] != str(root.resolve()):
                    raise ValueError("CLI verify requires declared project deliverables; run CLI export first")
                findings = verify_research_outputs(spec, timeline, args.out)
                print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False))
                return 1 if findings else 0
        else:
            audio = load_structured_file(args.audio)
            if args.command == "timeline":
                result = build_timeline(spec, audio, profile_settings(spec, args.profile)["fps"])
                _write(args.out, result)
            else:
                render_project(spec, audio, load_structured_file(args.timeline),
                    source=args.source, out=args.out, profile=args.profile,
                    theme_name=args.theme, theme_file=args.theme_file, font_file=args.font_file, root=root,
                    input_paths=(args.spec, args.audio, args.timeline),
                    slides=[s.strip() for s in args.slides.split(",") if s.strip()] if args.slides is not None else None)
        print(json.dumps({"ok": True, "output": str(args.out.resolve())}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

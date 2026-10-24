"""Same encoded visuals for narrated MP4 and silent Manim Slides PowerPoint.

``root`` is the render/output directory containing render-manifest.json. All
checks read actual bytes. No model inference, approvals or final copy are made.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
import xml.etree.ElementTree as ET
import zipfile

from postprocess_pptx import (A_NS, P_NS, add_static_fallback,
                             resolve_target, update_relationship_xml)
from .spec import content_hash, validate_spec, validate_text_review
from .timeline import require_narrated, validate_timeline
from .remote_worker import require_pcm_signal
from .voice import validate_audio_identity

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def run(args):
    result = subprocess.run(args, capture_output=True)
    if result.returncode:
        raise ValueError(f"{args[0]} failed: {result.stderr.decode(errors='replace')[-3000:]}")
    return result.stdout


def ffmpeg(*args):
    return run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *map(str, args)])


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                           "-show_format", "-of", "json", str(path)]))


def frame_hashes(path):
    output = ffmpeg("-i", path, "-map", "0:v:0", "-an", "-pix_fmt", "rgb24",
                    "-f", "framehash", "-hash", "sha256", "-").decode()
    return [line.rsplit(",", 1)[-1].strip() for line in output.splitlines() if not line.startswith("#")]


def _video(path, timing, settings, silent=True):
    streams = probe(path)["streams"]
    videos = [s for s in streams if s["codec_type"] == "video"]
    if len(videos) != 1:
        raise ValueError(f"{path}: expected one video stream")
    v = videos[0]
    if (int(v["nb_read_frames"]) != timing["frames"] or
            any(v[k] != settings[k] for k in ("width", "height")) or
            Fraction(v["avg_frame_rate"]) != settings["fps"] or
            abs(float(v["duration"]) - timing["frames"] / settings["fps"]) > .0011):
        raise ValueError(f"{path}: video frames, duration or profile mismatch")
    # Manim's MP4 movie header can quantize duration to milliseconds. Check
    # actual frame PTS independently, to one track tick, rather than hiding
    # drift behind a broad container-duration tolerance.
    frames = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_frames", "-show_entries", "frame=best_effort_timestamp", "-of", "json", str(path)]))["frames"]
    tick = Fraction(v["time_base"])
    if len(frames) != timing["frames"] or any(abs(int(f["best_effort_timestamp"]) * tick - Fraction(i, settings["fps"])) > tick for i, f in enumerate(frames)):
        raise ValueError(f"{path}: video frame timestamps drift from frozen frame boundaries")
    audios = [s for s in streams if s["codec_type"] == "audio"]
    if (silent and audios) or (not silent and len(audios) != 1):
        raise ValueError(f"{path}: {'silent clip contains audio' if silent else 'expected one narration stream'}")
    return v


def validate_frozen(spec, timeline):
    require_narrated(spec, timeline)
    if timeline.get("schema_version") != "research-timeline-1":
        raise ValueError("narrated workflow requires research-timeline-1")
    errors = validate_text_review(spec)
    if errors:
        raise ValueError("; ".join(errors))
    validate_audio_identity(spec, timeline["audio_identity"])
    if timeline["spec_hash"] != content_hash(spec):
        raise ValueError("timeline spec_hash is stale")
    payload = {k: v for k, v in timeline.items() if k != "timeline_hash"}
    if timeline["timeline_hash"] != content_hash(payload):
        raise ValueError("timeline hash is altered")
    if len(timeline["slides"]) != len(spec["slides"]):
        raise ValueError("timeline slide inventory mismatch")
    fps, cursor = timeline["fps"], 0
    for slide, timing in zip(spec["slides"], timeline["slides"]):
        start = cursor
        if timing["id"] != slide["id"] or len(timing["beats"]) != len(slide["beats"]):
            raise ValueError("timeline slide/beat order mismatch")
        for beat, cue in zip(slide["beats"], timing["beats"]):
            if cue["id"] != beat["id"] or cue["slide_id"] != slide["id"] or cue["narration_hash"] != content_hash(beat["narration"]):
                raise ValueError("timeline narration is stale")
            if sha(cue["path"]) != cue["sha256"]:
                raise ValueError("WAV sha256 mismatch")
            with wave.open(cue["path"], "rb") as wav:
                actual = (wav.getnframes(), wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
                if actual != tuple(cue[k] for k in ("sample_count", "sample_rate", "channels", "sample_width")) or wav.getcomptype() != "NONE":
                    raise ValueError("WAV sample metadata mismatch")
                payload = wav.readframes(actual[0])
                if len(payload) != actual[0] * actual[2] * actual[3]:
                    raise ValueError("truncated WAV")
                require_pcm_signal(payload, actual[3])
            frames = (actual[0] * fps + actual[1] - 1) // actual[1]
            expected = (cursor, cursor + frames, cursor - start, cursor + frames - start, frames)
            if tuple(cue[k] for k in ("start_frame", "end_frame", "local_start_frame", "local_end_frame", "frames")) != expected:
                raise ValueError("timeline cue boundaries mismatch")
            cursor += frames
        if (timing["start_frame"], timing["end_frame"], timing["frames"]) != (start, cursor, cursor - start):
            raise ValueError("timeline slide boundaries mismatch")
    if cursor != timeline["total_frames"] or timeline["duration_seconds"] != cursor / fps:
        raise ValueError("timeline total duration mismatch")


def validate_render_slide(item, timing, settings):
    """Validate retained evidence, not only its previous success flag."""
    for key in ("master", "trace", "slides_json", "qa"):
        expected = item[key + "_sha256"]
        if sha(item[key]) != expected:
            raise ValueError(f"{item['slide_id']}: {key} sha256 mismatch")
        if not Path(item[key]).is_file():
            raise ValueError(f"{item['slide_id']}: missing {key}")
    _video(item["master"], timing, settings)
    trace = [json.loads(line) for line in Path(item["trace"]).read_text().splitlines()]
    if [r["local_frame"] for r in trace] != list(range(timing["frames"])):
        raise ValueError("trace does not cover every actual output frame")
    if any(r.get("findings") for r in trace):
        raise ValueError("trace contains layout findings")
    # Re-run the geometric policy on the original observations as well.
    from .layout import check_frame
    qa = read_json(item["qa"])
    if (not qa["ok"] or qa.get("error") or qa.get("findings") or
            qa["frames"] != timing["frames"] or qa["expected_frames"] != timing["frames"] or
            qa["slide_id"] != item["slide_id"] or qa["fps"] != settings["fps"]):
        raise ValueError("invalid per-frame QA evidence")
    if any(check_frame(r["objects"], r["frame"], qa["layout"],
                       contacts=qa.get("math_contacts", ())) for r in trace):
        raise ValueError("retained geometry fails layout policy")
    contacts = qa.get("math_contacts", [])
    for record in trace:
        observed = record.get("math_contacts", [])
        # Later beats may declare a future relationship. Every recorded identity
        # must belong to QA, and every *active* QA relationship must be observed.
        active = [c for c in contacts if c["start_frame"] <= record["frame"] < c["end_frame"]]
        if (not isinstance(observed, list) or any(c not in contacts for c in observed)
                or any(c not in observed for c in active)):
            raise ValueError("retained math contact identity differs between trace and QA")
    if len(qa["beats"]) != len(timing["beats"]):
        raise ValueError("QA beat inventory mismatch")
    original_start = trace[0]["frame"]
    for actual, cue in zip(qa["beats"], timing["beats"]):
        if (actual["id"] != cue["id"] or actual["animation_frames"] + actual["wait_frames"] != cue["frames"]
                or actual["wait_frames"] <= 0 or actual["start_frame"] != cue["local_start_frame"]
                or actual["end_frame"] != cue["local_end_frame"]):
            raise ValueError("QA beat timing mismatch")
    if [r["frame"] for r in trace] != list(range(original_start, original_start + timing["frames"])):
        raise ValueError("original trace global frame continuity mismatch")
    if item.get("reused"):
        mapping_path = item["frame_mapping"]
        if sha(mapping_path) != item["frame_mapping_sha256"]:
            raise ValueError("derived frame mapping sha256 mismatch")
        mapping = [json.loads(line) for line in Path(mapping_path).read_text().splitlines()]
        expected = [{"local_frame": r["local_frame"], "frame": item["start_frame"] + r["local_frame"],
            "observed_frame": r["frame"], "source_trace": item["trace"],
            "source_trace_sha256": item["trace_sha256"]} for r in trace]
        if mapping != expected:
            raise ValueError("derived frame mapping differs from original observations")
    elif original_start != item["start_frame"]:
        raise ValueError("original frame offset differs without a derived mapping")
    return trace


def _inputs(spec, timeline, root, profile):
    from build_research import profile_settings, slide_dependency_hash
    validate_frozen(spec, timeline)
    manifest = read_json(root / "render-manifest.json")
    require_narrated(spec, manifest)
    if manifest.get("schema_version") != "research-render-1":
        raise ValueError("narrated workflow requires research-render-1")
    from common import load_structured_file
    from .themes import load_theme
    try:
        theme_input = manifest["theme_input"]
        file = theme_input["file"]
        overrides = None
        if file:
            path = Path(file["path"])
            if str(path.resolve()) != file["resolved_path"] or sha(path) != file["sha256"]:
                raise ValueError("effective theme file identity changed")
            overrides = load_structured_file(path)
        if load_theme(theme_input["name"], overrides) != manifest["theme"]:
            raise ValueError("effective theme values changed")
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError(f"render theme dependency changed; rerender before export: {exc}") from exc
    settings = profile_settings(spec, profile)
    if (not manifest["ok"] or manifest["settings"] != settings or manifest["profile"] != profile or
            settings["fps"] != timeline["fps"] or manifest["timeline_hash"] != timeline["timeline_hash"]):
        raise ValueError("render profile/timeline mismatch")
    if [s["slide_id"] for s in manifest["slides"]] != [s["id"] for s in timeline["slides"]]:
        raise ValueError("missing or out-of-order rendered slide")
    source = Path(manifest["source"]["path"])
    actual_sources = {str(p): sha(p) for p in sorted(source.parent.rglob("*.py"))}
    if sha(source) != manifest["source"]["sha256"] or actual_sources != manifest["source_files"]:
        raise ValueError("render source dependencies changed; rerender before export")
    if manifest["font"]["file"] and sha(manifest["font"]["file"]) != manifest["font"]["sha256"]:
        raise ValueError("render font dependency changed")
    for item, timing in zip(manifest["slides"], timeline["slides"]):
        if item["dependency_hash"] != slide_dependency_hash(spec, timing, manifest):
            raise ValueError("render local dependency hash is stale")
        if any(item[k] != timing[k] for k in ("frames", "start_frame", "end_frame")):
            raise ValueError("render slide offsets mismatch")
        validate_render_slide(item, timing, settings)
    return manifest


def assemble_audio(timeline, path):
    """Place each cue at its frame boundary, padding its end (never speech)."""
    cues = [b for s in timeline["slides"] for b in s["beats"]]
    rate = math.lcm(timeline["fps"], max(b["sample_rate"] for b in cues))
    channels = max(b["channels"] for b in cues)
    cursor = 0
    with wave.open(str(path), "wb") as out:
        out.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        for cue in cues:
            start = cue["start_frame"] * rate // timeline["fps"]
            end = cue["end_frame"] * rate // timeline["fps"]
            if (cue["sample_rate"], cue["channels"], cue["sample_width"]) == (rate, channels, 2):
                with wave.open(cue["path"], "rb") as wav:
                    data = wav.readframes(wav.getnframes())
            else:
                data = ffmpeg("-i", cue["path"], "-ar", rate, "-ac", channels, "-f", "s16le", "-")
            count = len(data) // (channels * 2)
            if cursor != start or count > end - start:
                raise ValueError("audio resampling would overrun cue boundary; refusing to truncate speech")
            out.writeframes(data)
            out.writeframes(bytes((end - start - count) * channels * 2))
            cursor = end
    return {"path": str(path), "sha256": sha(path), "sample_count": cursor,
            "sample_rate": rate, "channels": channels, "sample_width": 2}


def _aac(wav, path):
    with wave.open(str(wav), "rb") as source:
        rate = source.getframerate()
    ffmpeg("-i", wav, "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k", "-movie_timescale", rate, path)


def _codec_padding(path):
    packets = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets",
        "-show_entries", "packet=side_data_list", "-of", "json", str(path)]))["packets"]
    return {"codec_priming_samples": sum(s.get("skip_samples", 0) for p in packets for s in p.get("side_data_list", [])),
            "codec_tail_samples": sum(s.get("discard_padding", 0) for p in packets for s in p.get("side_data_list", []))}


def _audio_digest(path):
    payload = ffmpeg("-i", path, "-map", "0:a:0", "-f", "s16le", "-")
    require_pcm_signal(payload)
    return hashlib.sha256(payload).hexdigest()


def _poster(master, trace, destination):
    from PIL import Image, ImageStat
    # Prefer a stable, content-bearing frame. A blank terminal frame is never
    # accepted merely because it happens to be the last frame.
    candidates = [i for i in range(len(trace) - 1, -1, -1)
                  if any(o.get("visible") for o in trace[i]["objects"])
                  and (i == 0 or trace[i]["objects"] == trace[i - 1]["objects"])]
    for index in candidates:
        ffmpeg("-i", master, "-vf", f"select=eq(n\\,{index})", "-frames:v", 1, destination)
        with Image.open(destination) as im:
            if max(ImageStat.Stat(im.convert("RGB")).stddev) > 2:
                return index
    raise ValueError(f"no stable content-bearing poster frame: {master}")


def _package_ppt(render, slides, target):
    from manim_slides.config import PresentationConfig, SlideConfig
    from manim_slides.convert import PowerPoint
    configs = [PresentationConfig(slides=[SlideConfig(file=s["clip"], rev_file=s["clip"], notes=s["notes"])],
                                  resolution=(render["settings"]["width"], render["settings"]["height"])) for s in slides]
    # Installed Manim Slides uses an etree xpath implementation incompatible
    # with newer python-pptx. Disable its automatic trigger editing, then apply
    # the same delay=0 to its real OOXML movie timing below.
    PowerPoint(presentation_configs=configs, width=render["settings"]["width"],
               height=render["settings"]["height"], auto_play_media=False).convert_to(target)
    with zipfile.ZipFile(target) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    for i, slide in enumerate(slides, 1):
        rel = f"ppt/slides/_rels/slide{i}.xml.rels"
        members[rel], movie, poster = update_relationship_xml(members[rel], rel_path=rel, poster_number=i)
        members[poster] = Path(slide["poster"]).read_bytes()
        member = f"ppt/slides/slide{i}.xml"
        xml = ET.fromstring(members[member])
        conditions = xml.findall(f".//{{{P_NS}}}video//{{{P_NS}}}cond")
        if len(conditions) != 1:
            raise ValueError("expected one movie autoplay timing condition")
        conditions[0].set("delay", "0")
        members[member], _ = add_static_fallback(ET.tostring(xml), slide_number=i)
        slide.update({"movie_member": movie, "poster_member": poster})
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _protected_inputs(spec, timeline, render, root, project_root=None, input_paths=()):
    protected = {Path(b["path"]).resolve() for s in timeline["slides"] for b in s["beats"]}
    protected.update(Path(p).resolve() for p in render["source_files"])
    protected.update(Path(p).resolve() for p in (*render.get("input_paths", []), *input_paths))
    protected.add((root / "render-manifest.json").resolve())
    project_root = project_root or render.get("project_root")
    if project_root:
        project_root = Path(project_root)
        protected.update((project_root / p).resolve() for p in
            ["planning/deck.yaml", "planning/evidence-map.md", *spec["project"].get("source_files", [])])
    theme_file = render.get("theme_input", {}).get("file")
    if theme_file:
        protected.update(Path(theme_file[k]).resolve() for k in ("path", "resolved_path"))
    if render["font"]["file"]:
        protected.add(Path(render["font"]["file"]).resolve())
    protected.update(Path(item[key]).resolve() for item in render["slides"]
                     for key in ("master", "trace", "qa", "slides_json"))
    return protected


def _guard_export_writes(spec, timeline, render, root, destinations=(), project_root=None, input_paths=()):
    staging = root / "export"
    writes = [root / "export-manifest.json", *destinations]
    writes.extend(staging / name for name in ("visual-concat.txt", "visual.mp4", "narration.wav",
                                             "narration.m4a", "narrated.mp4", "silent-slides.pptx"))
    for i in range(1, len(spec["slides"]) + 1):
        writes.extend([staging / f"slide-{i:04d}.mp4", staging / f"poster-{i:04d}.png"])
    protected = _protected_inputs(spec, timeline, render, root, project_root, input_paths)
    existing_identities = {(p.stat().st_dev, p.stat().st_ino) for p in protected if p.is_file()}
    if (protected.intersection(Path(p).resolve() for p in writes)
            or any(p.is_file() and (p.stat().st_dev, p.stat().st_ino) in existing_identities for p in writes)):
        raise ValueError("outputs collide with protected source/audio/render inputs")


def export_media(spec: dict, timeline: dict, root: Path, profile: str) -> dict:
    root = Path(root).resolve()
    render = _inputs(spec, timeline, root, profile)
    _guard_export_writes(spec, timeline, render, root)
    destination = root / "export"
    destination.mkdir(exist_ok=True)
    manifest_path = root / "export-manifest.json"
    write_json(manifest_path, {"ok": False, "error": "export in progress"})
    slides, signatures = [], []
    for i, (item, timing, slide) in enumerate(zip(render["slides"], timeline["slides"], spec["slides"])):
        clip = destination / f"slide-{i + 1:04d}.mp4"
        shutil.copyfile(item["master"], clip)
        v = _video(clip, timing, render["settings"])
        signatures.append({k: v.get(k) for k in ("codec_name", "profile", "level", "width", "height", "pix_fmt", "time_base", "r_frame_rate")})
        poster = destination / f"poster-{i + 1:04d}.png"
        trace = validate_render_slide(item, timing, render["settings"])
        frame = _poster(clip, trace, poster)
        slides.append({"slide_id": slide["id"], "clip": str(clip), "clip_sha256": sha(clip),
            "poster": str(poster), "poster_sha256": sha(poster), "poster_local_frame": frame,
            "poster_global_frame": timing["start_frame"] + frame,
            "notes": "\n".join(b["narration"] for b in slide["beats"]),
            **{k: timing[k] for k in ("frames", "start_frame", "end_frame")}})
    if any(sig != signatures[0] for sig in signatures):
        raise ValueError("scene masters have incompatible stream-copy encoding settings")
    concat = destination / "visual-concat.txt"
    # Filenames are generated locally, so the concat grammar never receives a
    # caller-controlled quoted path, even when project paths contain apostrophes.
    concat.write_text("".join(f"file '{Path(s['clip']).name}'\nduration {s['frames'] / timeline['fps']:.12f}\n" for s in slides))
    visual = destination / "visual.mp4"
    ffmpeg("-f", "concat", "-safe", 1, "-i", concat, "-map", "0:v:0", "-an", "-c:v", "copy",
           "-movie_timescale", timeline["fps"] * 1024, visual)
    audio = assemble_audio(timeline, destination / "narration.wav")
    aac = destination / "narration.m4a"
    _aac(audio["path"], aac)
    output = destination / "narrated.mp4"
    ffmpeg("-i", visual, "-i", aac, "-map", "0:v:0", "-map", "1:a:0",
           "-c", "copy", "-movie_timescale", math.lcm(timeline["fps"] * 1024, audio["sample_rate"]),
           "-movflags", "+faststart", output)
    decoded_bytes = len(ffmpeg("-i", aac, "-f", "s16le", "-"))
    audio.update({"aac": str(aac), "aac_sha256": sha(aac), "codec": "aac", "bitrate": "192k",
        "codec_start_seconds": float(next(s for s in probe(output)["streams"] if s["codec_type"] == "audio")["start_time"]),
        "decoded_samples": decoded_bytes // (audio["channels"] * 2),
        **_codec_padding(output),
        "decoded_tail_samples": decoded_bytes // (audio["channels"] * 2) - audio["sample_count"],
        "priming": "AAC encoder delay is carried by MP4 edit-list/skip-samples metadata; no -shortest or speech trimming"})
    pptx = destination / "silent-slides.pptx"
    _package_ppt(render, slides, pptx)
    result = {"schema_version": "research-export-1", "ok": False, "profile": profile,
        "timeline_hash": timeline["timeline_hash"], "spec_hash": content_hash(spec),
        "settings": render["settings"], "mp4": str(output), "pptx": str(pptx), "visual": str(visual),
        "audio": audio, "slides": slides}
    write_json(manifest_path, result)
    findings = verify_research_outputs(spec, timeline, root)
    if findings:
        result["findings"] = findings
        write_json(manifest_path, result)
        raise ValueError("export verification failed: " + json.dumps(findings, ensure_ascii=False))
    result["ok"] = True
    write_json(manifest_path, result)
    return result


def _delivery_paths(spec, project_root):
    project_root = Path(project_root).resolve()
    errors = validate_spec(spec, project_root)
    if errors:
        raise ValueError("; ".join(errors))
    paths = {key: (project_root / spec["outputs"][key]).resolve() for key in ("video", "pptx", "speech")}
    if len(set(paths.values())) != 3:
        raise ValueError("outputs must name distinct deliverables")
    return paths


def research_speech(spec, timeline, audio):
    """Deterministic manuscript from verified PCM timing and synthesis input text.

    This never calls the legacy notes/character-count speech estimator. Sample
    fractions and frame intervals are retained alongside human-readable seconds.
    """
    errors = validate_timeline(timeline, spec, audio, timeline["fps"])
    if errors:
        raise ValueError("; ".join(errors))
    pronunciation = spec["voice"].get("pronunciation", {})
    if audio.get("settings", {}).get("pronunciation", {}) != pronunciation:
        raise ValueError("audio pronunciation settings differ from current spec")
    inventory = {(item["slide_id"], item["beat_id"]): item for item in audio["audio"]}
    lines = [f"# {spec['project']['title']}", "",
        f"总时长：{timeline['total_frames'] / timeline['fps']:.6f} 秒；{timeline['total_frames']} 帧；{timeline['fps']} fps。", ""]
    if pronunciation:
        lines.extend(["## 发音对应", ""])
        lines.extend(f"- {original}：{replacement}" for original, replacement in pronunciation.items())
        lines.append("")
    for slide, timing in zip(spec["slides"], timeline["slides"]):
        lines.extend([f"## {slide['id']} {slide['title']}", "",
            f"全片帧：[{timing['start_frame']},{timing['end_frame']})；实际时长：{timing['frames'] / timeline['fps']:.6f} 秒。", ""])
        for beat, cue in zip(slide["beats"], timing["beats"]):
            item = inventory[(slide["id"], beat["id"])]
            spoken = beat["narration"]
            for original, replacement in pronunciation.items():
                if not original or not isinstance(replacement, str):
                    raise ValueError("pronunciation must map nonempty strings to strings")
                spoken = spoken.replace(original, replacement)
            if item["spoken_text"] != spoken:
                raise ValueError("synthesis input spoken_text differs from current pronunciation mapping")
            lines.extend([f"### {beat['id']}", "", "最终旁白：", "", beat["narration"], "",
                "合成输入文本：", "", item["spoken_text"], "",
                f"全片帧：[{cue['start_frame']},{cue['end_frame']})；页内帧：[{cue['local_start_frame']},{cue['local_end_frame']})。",
                f"全片时间：[{cue['start_frame'] / timeline['fps']:.6f},{cue['end_frame'] / timeline['fps']:.6f}) 秒；节拍时长：{cue['frames'] / timeline['fps']:.6f} 秒。",
                f"WAV 实际时长：{cue['sample_count']}/{cue['sample_rate']} = {cue['sample_count'] / cue['sample_rate']:.6f} 秒；尾部静音：{cue['padding_seconds']:.6f} 秒。", ""])
    return "\n".join(lines) + "\n"


def publish_research_outputs(spec, timeline, audio, root, project_root, profile, *, input_paths=()):
    """CLI release wrapper: honor declared destinations and publish true-timing speech."""
    require_narrated(spec, timeline, audio)
    root, project_root = Path(root).resolve(), Path(project_root).resolve()
    paths = _delivery_paths(spec, project_root)
    # Internal clips/posters/audio remain verifier inputs after publication.
    # Reserve the whole staging directory except each final output's own slot.
    staging_dir = (root / "export").resolve()
    final_slots = {"video": staging_dir / "narrated.mp4",
                   "pptx": staging_dir / "silent-slides.pptx"}
    if any(path.is_relative_to(staging_dir) and path != final_slots.get(key)
           for key, path in paths.items()):
        raise ValueError("outputs collide with reserved export staging inputs")
    manuscript = research_speech(spec, timeline, audio)
    render = read_json(root / "render-manifest.json")
    _guard_export_writes(spec, timeline, render, root, paths.values(), project_root, input_paths)
    result = export_media(spec, timeline, root, profile)
    staging = {"video": Path(result["mp4"]), "pptx": Path(result["pptx"])}
    result.update({"ok": False, "mp4": str(paths["video"]), "pptx": str(paths["pptx"]),
        "delivery": {"project_root": str(project_root), "speech": str(paths["speech"]),
            "audio_manifest": json.loads(json.dumps({key: audio.get(key) for key in ("job_id", "settings", "audio")}))}})
    manifest_path = root / "export-manifest.json"
    write_json(manifest_path, result)
    for key, source in staging.items():
        paths[key].parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != paths[key]:
            shutil.copyfile(source, paths[key])
    paths["speech"].parent.mkdir(parents=True, exist_ok=True)
    paths["speech"].write_text(manuscript, encoding="utf-8")
    result["delivery"]["speech_sha256"] = sha(paths["speech"])
    write_json(manifest_path, result)
    findings = verify_research_outputs(spec, timeline, root)
    if findings:
        result["findings"] = findings
        write_json(manifest_path, result)
        raise ValueError("published deliverables failed verification: " + json.dumps(findings, ensure_ascii=False))
    result["ok"] = True
    write_json(manifest_path, result)
    return result


def _verify_package(path, slides, settings, temp):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError("corrupt PPTX archive")
        names = archive.namelist()
        expected = [f"ppt/slides/slide{i}.xml" for i in range(1, len(slides) + 1)]
        if sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)) != sorted(expected):
            raise ValueError("PPT slide inventory mismatch")
        # Verify real presentation order, not numeric filenames alone.
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        rels = ET.fromstring(archive.read("ppt/_rels/presentation.xml.rels"))
        targets = {r.get("Id"): resolve_target("ppt/_rels/presentation.xml.rels", r.get("Target")) for r in rels}
        order = [targets[n.get(f"{{{R_NS}}}id")] for n in presentation.findall(f".//{{{P_NS}}}sldId")]
        if order != expected:
            raise ValueError("PPT slide order mismatch")
        size = presentation.find(f"{{{P_NS}}}sldSz")
        if size is None:
            raise ValueError("PPT slide size is missing")
        if int(size.get("cx")) * 9 != int(size.get("cy")) * 16:
            raise ValueError("PPT aspect ratio is not 16:9")
        used_movies = set()
        for i, slide in enumerate(slides, 1):
            member = f"ppt/slides/slide{i}.xml"
            relpath = f"ppt/slides/_rels/slide{i}.xml.rels"
            relationships = ET.fromstring(archive.read(relpath))
            by_id = {r.get("Id"): r for r in relationships}
            videos = [r for r in relationships if r.get("Type", "").endswith("/video")]
            if len(videos) != 1 or videos[0].get("TargetMode") == "External":
                raise ValueError("expected one embedded movie per PPT slide")
            movie = resolve_target(relpath, videos[0].get("Target"))
            used_movies.add(movie)
            clip = temp / f"ppt-{i}.mp4"
            clip.write_bytes(archive.read(movie))
            _video(clip, slide, settings)
            if frame_hashes(clip) != slide["frame_hashes"]:
                raise ValueError(f"PPT slide {i}: decoded visual stream differs from master")
            xml = ET.fromstring(archive.read(member))
            pictures = xml.findall(f".//{{{P_NS}}}spTree/{{{P_NS}}}pic")
            if any(p.find(f".//{{{P_NS}}}cNvPr") is None for p in pictures):
                raise ValueError(f"PPT slide {i}: picture cNvPr node missing")
            movies = [p for p in pictures if p.find(f".//{{{A_NS}}}videoFile") is not None]
            fallback = [p for p in pictures if p.find(f".//{{{P_NS}}}cNvPr").get("name") == f"manim-static-poster-{i}"]
            if len(movies) != 1 or len(fallback) != 1 or pictures.index(fallback[0]) >= pictures.index(movies[0]):
                raise ValueError("PPT static fallback missing or not behind movie")
            video_rid = movies[0].find(f".//{{{A_NS}}}videoFile").get(f"{{{R_NS}}}link")
            media = movies[0].find(".//{http://schemas.microsoft.com/office/powerpoint/2010/main}media")
            if media is None:
                raise ValueError("PPT modern movie playback reference missing")
            for rid in (video_rid, media.get(f"{{{R_NS}}}embed")):
                if rid not in by_id or by_id[rid].get("TargetMode") == "External" or resolve_target(relpath, by_id[rid].get("Target")) != movie:
                    raise ValueError("PPT movie playback relationship mismatch")
            for pic in (movies[0], fallback[0]):
                blip = pic.find(f".//{{{A_NS}}}blip")
                if blip is None:
                    raise ValueError(f"PPT slide {i}: picture blip node missing")
                rid = blip.get(f"{{{R_NS}}}embed")
                poster = resolve_target(relpath, by_id[rid].get("Target"))
                if archive.read(poster) != Path(slide["poster"]).read_bytes():
                    raise ValueError("PPT poster/fallback relationship mismatch")
            if not any(c.get("delay") == "0" for c in xml.findall(f".//{{{P_NS}}}video//{{{P_NS}}}cond")):
                raise ValueError("PPT autoplay trigger missing")
            note_rels = [r for r in relationships if r.get("Type", "").endswith("/notesSlide")]
            if len(note_rels) != 1:
                raise ValueError("PPT narration notes missing")
            note = ET.fromstring(archive.read(resolve_target(relpath, note_rels[0].get("Target"))))
            texts = []
            for shape in note.findall(f".//{{{P_NS}}}sp"):
                ph = shape.find(f".//{{{P_NS}}}ph")
                if ph is not None and ph.get("type") == "body":
                    texts.extend("".join(p.itertext()) for p in shape.findall(f".//{{{A_NS}}}p"))
            if "\n".join(texts) != slide["notes"]:
                raise ValueError("PPT notes differ from canonical narration")
        image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf", ".svg"}
        media = {n for n in names if n.startswith("ppt/media/") and Path(n).suffix.lower() not in image_suffixes}
        if media != used_movies:
            raise ValueError("unreferenced or missing embedded movie inventory")


def verify_research_outputs(spec, timeline, root) -> list[dict]:
    """Return actionable failures; package presence and recorded ok are not proof."""
    try:
        require_narrated(spec, timeline)
        root = Path(root).resolve()
        result = read_json(root / "export-manifest.json")
        render = _inputs(spec, timeline, root, result["profile"])
        if result["timeline_hash"] != timeline["timeline_hash"] or result["spec_hash"] != content_hash(spec):
            raise ValueError("export manifest is stale")
        if [s["slide_id"] for s in result["slides"]] != [s["id"] for s in spec["slides"]]:
            raise ValueError("export slide inventory mismatch")
        if delivery := result.get("delivery"):
            paths = _delivery_paths(spec, delivery["project_root"])
            if (result["mp4"], result["pptx"], delivery["speech"]) != tuple(str(paths[k]) for k in ("video", "pptx", "speech")):
                raise ValueError("published paths differ from spec.outputs; staging is not a substitute")
            expected_speech = research_speech(spec, timeline, delivery["audio_manifest"]).encode("utf-8")
            if paths["speech"].read_bytes() != expected_speech or sha(paths["speech"]) != delivery["speech_sha256"]:
                raise ValueError("declared speech manuscript differs from verified real timing/narration/pronunciation")
        expected_hashes = []
        with tempfile.TemporaryDirectory(prefix="research-verify-") as dirname:
            temp = Path(dirname)
            for item, slide, timing, source in zip(result["slides"], spec["slides"], timeline["slides"], render["slides"]):
                if any(item[k] != timing[k] for k in ("frames", "start_frame", "end_frame")):
                    raise ValueError("export offsets mismatch")
                if item["notes"] != "\n".join(b["narration"] for b in slide["beats"]):
                    raise ValueError("export notes differ from canonical narration")
                _video(item["clip"], timing, render["settings"])
                hashes = frame_hashes(source["master"])
                if frame_hashes(item["clip"]) != hashes:
                    raise ValueError("export clip differs from master")
                item["frame_hashes"] = hashes
                expected_hashes.extend(hashes)
                index = item["poster_local_frame"]
                if not 0 <= index < timing["frames"] or item["poster_global_frame"] != timing["start_frame"] + index:
                    raise ValueError("poster frame offset mismatch")
                expected_poster = temp / "poster.png"
                ffmpeg("-i", source["master"], "-vf", f"select=eq(n\\,{index})", "-frames:v", 1, expected_poster)
                from PIL import Image, ImageStat
                with Image.open(item["poster"]) as poster, Image.open(expected_poster) as expected:
                    if poster.size != expected.size or poster.convert("RGB").tobytes() != expected.convert("RGB").tobytes() or max(ImageStat.Stat(poster.convert("RGB")).stddev) <= 2:
                        raise ValueError("poster is blank or differs from selected output frame")
            _video(result["mp4"], {"frames": timeline["total_frames"]}, render["settings"], silent=False)
            if frame_hashes(result["mp4"]) != expected_hashes:
                raise ValueError("narrated MP4 decoded frames differ from ordered slide masters")
            expected_audio = assemble_audio(timeline, temp / "expected.wav")
            if sha(result["audio"]["path"]) != expected_audio["sha256"]:
                raise ValueError("narration WAV differs from frame-aligned cues")
            _aac(expected_audio["path"], temp / "expected.m4a")
            if _audio_digest(result["mp4"]) != _audio_digest(temp / "expected.m4a"):
                raise ValueError("AAC narration is truncated, shifted, replaced or differs from frame-aligned cues")
            stream = next(s for s in probe(result["mp4"])["streams"] if s["codec_type"] == "audio")
            if stream["codec_name"] != "aac" or abs(float(stream["start_time"])) > 1 / expected_audio["sample_rate"] or abs(float(stream["duration"]) - timeline["duration_seconds"]) > 1 / expected_audio["sample_rate"]:
                raise ValueError("AAC stream start or duration mismatch (speech may be truncated)")
            _verify_package(result["pptx"], result["slides"], render["settings"], temp)
        return []
    except (OSError, ValueError, KeyError, TypeError, IndexError, ET.ParseError, zipfile.BadZipFile, wave.Error) as exc:
        return [{"code": "research_output_invalid", "message": str(exc)}]

"""Isolated voice-free CLI, actual tiny media, provenance and preservation guards."""
import copy
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import av
import numpy as np
import pytest

import build_research as cli
from research import media
from research.preview_timeline import build_preview_timeline
from research.spec import audience_copy, content_hash
from research.timeline import build_timeline, validate_timeline
from test_research_media import project as narrated_project


SOURCE = '''from manim import Circle
from research.preview_scene import SilentPreviewScene
class Tiny(SilentPreviewScene):
    def state_at(self, local_frame):
        return {"x": -2.0}
    def update_geometry(self, state):
        self.dot.move_to([state["x"], -1, 0])
    def construct(self):
        self.add(self.text("title", role="title").move_to([0, 2, 0]))
        self.dot = self.track("dot", Circle(radius=.15, color="#FF0000", fill_opacity=1, stroke_width=0), "shape")
        self.add(self.dot)
        self.preview_beat("hold")
'''


def approve_synthetic_fixture(spec):
    # Controlled test copy only: never generates approval for a real example.
    digest = content_hash(audience_copy(spec))
    spec["text_review"] = {"content_hash": digest, **{name: {
        "status": "approved", "content_hash": digest} for name in ("humanizer", "humanizer-zh")}}


@pytest.fixture(autouse=True)
def forbid_voice_and_ssh(monkeypatch):
    import research.voice
    def forbidden(*args, **kwargs):
        pytest.fail("silent preview attempted voice synthesis")
    monkeypatch.setattr(research.voice, "synthesize_remote", forbidden)
    popen = subprocess.Popen
    def guarded(args, *rest, **kwargs):
        executable = Path(args[0]).name if not isinstance(args, str) else args.split()[0]
        if executable in {"ssh", "scp", "say", "espeak", "tts"}:
            pytest.fail(f"silent preview attempted {executable}")
        return popen(args, *rest, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", guarded)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "planning").mkdir()
    source = root / "src/scenes.py"
    source.write_text(SOURCE)
    spec = {"schema_version": "research-preview-spec-1", "project": {
        "title": "测量", "theme": "midnight", "source_files": ["src/scenes.py"]},
        "slides": [{"id": "s", "scene_class": "Tiny", "screen_text": {"title": "测量"},
                    "beats": [{"id": "hold", "screen_text": ["title"]}]}]}
    approve_synthetic_fixture(spec)
    authored = {"schema_version": "research-authored-timeline-1", "mode": "silent-preview",
                "fps": 15, "slides": [{"id": "s", "beats": [{"id": "hold", "frames": 3}]}]}
    (root / "planning/deck.json").write_text(json.dumps(spec, ensure_ascii=False))
    (root / "planning/authored.json").write_text(json.dumps(authored))
    (root / "theme.json").write_text('{"line_width": 3}')
    (root / "old-movie.mp4").write_bytes(b"old encoded movie must remain untouched")
    from research.scene import ensure_font
    local_font = ensure_font()["file"]
    assert local_font, "preservation fixture requires the workstation's licensed local font"
    shutil.copyfile(local_font, root / "font.ttc")
    return root, spec, authored, source


def preview(project, out, **kwargs):
    root, spec, authored, source = project
    function = getattr(cli, "render_silent_preview", None)
    assert function is not None, "render_silent_preview entry point is missing"
    return function(spec, authored, source=source, out=out, root=root,
                    input_paths=(root / "planning/deck.json", root / "planning/authored.json"), **kwargs)


def snapshot(root):
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def test_cli_renders_no_voice_spec_and_preserves_raw_inputs(project, capsys):
    root, spec, authored, source = project
    before = snapshot(root)
    out = root.parent / "preview-cli"
    status = cli.main(["silent-preview", "--spec", str(root / "planning/deck.json"),
        "--authored-timeline", str(root / "planning/authored.json"), "--source", str(source), "--out", str(out)])
    assert status == 0, capsys.readouterr().out
    manifest = json.loads((out / "render-manifest.json").read_text())
    assert manifest["schema_version"] == "research-preview-render-1"
    assert manifest["mode"] == "silent-preview" and manifest["ok"] is True
    assert manifest["profile"] == "draft"
    item = manifest["slides"][0]
    assert item["has_audio"] is False and item["observed_frames"] == 3
    assert manifest["authored_hash"] == content_hash(authored)
    assert json.loads(Path(manifest["timeline"]["path"]).read_text())["mode"] == "silent-preview"
    assert manifest["spec_hash"] == content_hash(spec)
    for key in ("spec", "authored_timeline", "timeline"):
        assert media.sha(manifest[key]["path"]) == manifest[key]["sha256"]
    assert {p: (Path(p).read_bytes(), Path(p).stat().st_mtime_ns) for p in before} == before
    assert not list(out.rglob("*.wav"))


def test_standalone_cli_process_renders_silent_preview(project):
    root, _, _, source = project
    out = root.parent / "process-preview"
    proc = subprocess.run([sys.executable, str(Path(cli.__file__).resolve()), "silent-preview",
        "--spec", str(root / "planning/deck.json"), "--authored-timeline", str(root / "planning/authored.json"),
        "--source", str(source), "--out", str(out)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = media.read_json(out / "render-manifest.json")
    assert manifest["ok"] is True and manifest["mode"] == "silent-preview"
    assert manifest["slides"][0]["has_audio"] is False


@pytest.mark.parametrize("profile,fps,width,height", [("draft", 15, 960, 540), ("final", 60, 1920, 1080)])
def test_actual_tiny_profiles_have_exact_pts_frame_count_and_no_audio(project, profile, fps, width, height):
    root, _, authored, _ = project
    authored["fps"] = fps
    result = preview(project, root.parent / profile, profile=profile)
    item = result["slides"][0]
    assert result["profile"] == profile
    assert result["settings"] == {"width": width, "height": height, "fps": fps}
    with av.open(item["master"]) as clip:
        assert not clip.streams.audio
        frames = list(clip.decode(video=0))
    assert len(frames) == 3
    assert [(f.width, f.height) for f in frames] == [(width, height)] * 3
    assert [float(f.pts * f.time_base) for f in frames] == pytest.approx([0, 1/fps, 2/fps])
    assert media.read_json(item["qa"])["frames"] == 3


@pytest.mark.parametrize("profile,fps", [("draft", 60), ("final", 15)])
def test_profile_mismatch_fails_before_output_or_source_execution(project, profile, fps):
    root, _, authored, source = project
    authored["fps"] = fps
    source.write_text("raise AssertionError('source must not execute')")
    out = root.parent / "mismatch"
    with pytest.raises(ValueError, match="fps"):
        preview(project, out, profile=profile)
    assert not out.exists()


@pytest.mark.parametrize("fault", ["missing", "stale", "one_pass"])
def test_text_reviews_are_required_and_current_before_any_write(project, fault):
    root, spec, _, source = project
    if fault == "missing":
        spec.pop("text_review")
    elif fault == "stale":
        spec["slides"][0]["screen_text"]["title"] = "比较"
    else:
        spec["text_review"]["humanizer-zh"]["status"] = "pending"
    source.write_text("raise AssertionError('source must not execute')")
    out = root.parent / "review"
    with pytest.raises(ValueError, match="text_review"):
        preview(project, out)
    assert not out.exists()


@pytest.mark.parametrize("alias", ["existing", "input_directory", "symlink_input", "symlink_old", "ancestor", "hardlink"])
def test_output_guards_preserve_source_timing_font_theme_and_old_media(project, alias):
    root, _, _, source = project
    out = root.parent / "output"
    if alias == "existing":
        out.mkdir()
        (out / "keep.txt").write_text("existing output")
    elif alias == "input_directory":
        out = root / "src"
    elif alias.startswith("symlink"):
        out.symlink_to(source if alias == "symlink_input" else root / "old-movie.mp4")
    elif alias == "ancestor":
        link = root.parent / "alias-parent"
        link.symlink_to(root, target_is_directory=True)
        out = link / "new-preview"
    else:
        out.hardlink_to(root / "planning/authored.json")
    before = snapshot(root)
    with pytest.raises(ValueError, match="fresh|exist|symlink|protected"):
        preview(project, out, theme_name="custom", theme_file=root / "theme.json", font_file=root / "font.ttc")
    assert snapshot(root) == before
    assert not (root / "new-preview").exists()


@pytest.mark.parametrize("theme", ["midnight", "paper", "slate", "custom"])
def test_theme_loading_keeps_fixed_roles_in_actual_qa(project, theme):
    root, _, _, _ = project
    result = preview(project, root.parent / theme, theme_name=theme,
                     theme_file=root / "theme.json" if theme == "custom" else None)
    qa = media.read_json(result["slides"][0]["qa"])
    assert qa["theme"]["name"] == theme
    assert qa["layout"]["font_sizes"] == {"title": 48, "body": 30, "caption": 20}
    assert result["font"]["family"] == "Microsoft YaHei"


def red_center(master):
    with av.open(master) as clip:
        pixels = next(clip.decode(video=0)).to_ndarray(format="rgb24")
    red = (pixels[:, :, 0] > 170) & (pixels[:, :, 1] < 70) & (pixels[:, :, 2] < 70)
    return np.nonzero(red)[1].mean()


@pytest.mark.parametrize("kind", ["source", "sibling"])
def test_same_size_same_timestamp_source_change_updates_actual_pixels_and_identity(project, kind):
    root, _, _, source = project
    changed = source
    if kind == "sibling":
        changed = source.parent / "preview_fixture_position.py"
        changed.write_text("X = -2.0\n")
        source.write_text(SOURCE.replace("from manim import Circle", "from manim import Circle\nfrom preview_fixture_position import X")
                          .replace('return {"x": -2.0}', 'return {"x": X}'))
    first = preview(project, root.parent / "first")
    stat = changed.stat()
    changed.write_text(changed.read_text().replace("-2.0", "+2.0"))
    os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    second = preview(project, root.parent / "second")
    assert first["source_files"] != second["source_files"]
    assert first["slides"][0]["dependency_hash"] != second["slides"][0]["dependency_hash"]
    assert red_center(first["slides"][0]["master"]) < 400
    assert red_center(second["slides"][0]["master"]) > 600


@pytest.mark.parametrize("prior", [False, True], ids=["missing-parents", "prior-parents"])
@pytest.mark.parametrize("fail", [False, True], ids=["success", "exception"])
def test_namespace_parent_and_nested_children_restore_import_state(tmp_path, monkeypatch, prior, fail):
    # Removing ancestor inventory leaks namespace modules or mutates existing
    # parent attributes, even when leaf-module and meta-path cleanup succeeds.
    package = "preview_fixture_namespace"
    nested = package + ".nested"
    child = nested + ".helper"
    source = tmp_path / "scenes.py"
    source.write_text("# controlled entry fixture\n")
    directory = tmp_path / package / "nested"
    directory.mkdir(parents=True)
    helper = directory / "helper.py"
    helper.write_text('VALUE = "prior-state"\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    def modules():
        return {name: module for name, module in sys.modules.items()
                if name == package or name.startswith(package + ".")}
    original = modules()
    for name in original:
        sys.modules.pop(name)
    try:
        if prior:
            importlib.import_module(child)
        previous = modules()
        helper.write_text('VALUE = "hashed-snapshot"\n')
        sources = {path: path.read_bytes() for path in (source, helper)}
        helper.write_text('VALUE = "unhashed-disk"\n')
        path_before, finders_before = tuple(sys.path), tuple(sys.meta_path)
        active = {}
        def execute():
            with cli._preview_imports(source, sources):
                imported = importlib.import_module(child)
                assert imported.VALUE == "hashed-snapshot"
                active.update(modules())
                assert set(active) == {package, nested, child}
                if fail:
                    raise RuntimeError("controlled preview failure")
        if fail:
            with pytest.raises(RuntimeError, match="controlled preview failure"):
                execute()
        else:
            execute()
        assert tuple(sys.meta_path) == finders_before
        assert tuple(sys.path) == path_before
        assert modules() == previous
        if prior:
            assert all(active[name] is not previous[name] for name in previous)
            assert previous[package].nested is previous[nested]
            assert previous[nested].helper is previous[child]
            assert previous[child].VALUE == "prior-state"
    finally:
        for name in modules():
            sys.modules.pop(name)
        sys.modules.update(original)


def test_timing_and_theme_changes_change_preview_identity(project):
    root, _, authored, _ = project
    first = preview(project, root.parent / "one")
    authored["slides"][0]["beats"][0]["frames"] = 4
    second = preview(project, root.parent / "two")
    third = preview(project, root.parent / "three", theme_name="paper")
    assert first["authored_hash"] != second["authored_hash"]
    assert first["timeline_hash"] != second["timeline_hash"]
    assert first["slides"][0]["dependency_hash"] != second["slides"][0]["dependency_hash"]
    assert second["slides"][0]["dependency_hash"] != third["slides"][0]["dependency_hash"]


def test_audit_failure_keeps_false_manifest_and_failure_frame(project):
    from research.scene import AuditFailure
    root, _, _, source = project
    source.write_text(SOURCE.replace('self.add(self.dot)', 'self.dot.shift([0, 10, 0])\n        self.add(self.dot)')
                      .replace('self.dot.move_to([state["x"], -1, 0])', 'self.dot.move_to([state["x"], 10, 0])'))
    out = root.parent / "failed"
    with pytest.raises(AuditFailure, match="audit|finding"):
        preview(project, out)
    manifest = media.read_json(out / "render-manifest.json")
    assert manifest["ok"] is False and manifest["error"]
    assert list(out.rglob("qa.json")) and list(out.rglob("*.png"))


@pytest.mark.parametrize("schema,mode", [("research-preview-timeline-1", "silent-preview"),
    ("research-preview-render-1", "silent-preview"), ("research-timeline-1", "silent-preview")])
def test_narrated_library_boundaries_reject_preview_before_audio_reads(project, schema, mode):
    root, spec, authored, _ = project
    frozen = build_preview_timeline(spec, authored, 15)
    frozen.update(schema_version=schema, mode=mode)
    # A valid preview spec alone must not mask missing artifact-mode checks.
    spec = {"schema_version": "0.2"}
    assert "narrated" in ";".join(validate_timeline(frozen, spec, {}, 15))
    with pytest.raises(ValueError, match="narrated"):
        build_timeline(spec, frozen, 15)
    for call in [lambda: media.validate_frozen(spec, frozen),
                 lambda: media.export_media(spec, frozen, root / "absent", "draft"),
                 lambda: media.publish_research_outputs(spec, frozen, {}, root / "absent", root, "draft")]:
        with pytest.raises(ValueError, match="narrated"):
            call()
    findings = media.verify_research_outputs(spec, frozen, root / "absent")
    assert findings and "narrated" in findings[0]["message"]


@pytest.mark.parametrize("schema", ["research-preview-timeline-1", "research-preview-render-1"])
@pytest.mark.parametrize("command", ["render", "export", "verify"])
def test_narrated_cli_with_narrated_spec_rejects_preview_artifacts_before_audio(project, schema, command, capsys):
    root, _, _, source = project
    template = Path(cli.__file__).resolve().parents[1] / "assets/research-template"
    shutil.copytree(template, root, dirs_exist_ok=True)
    bad = root / "preview-artifact.json"
    bad.write_text(json.dumps({"schema_version": schema, "mode": "silent-preview"}))
    args = [command, "--spec", str(root / "planning/deck.yaml"), "--audio", str(root / "MISSING.json"),
            "--timeline", str(bad), "--out", str(root / "absent")]
    if command == "render":
        args += ["--source", str(source)]
    assert cli.main(args) == 1
    assert "narrated" in capsys.readouterr().out
    assert not (root / "absent").exists()


@pytest.mark.parametrize("command", ["timeline", "render", "export", "verify"])
def test_narrated_cli_rejects_preview_before_loading_nonexistent_audio(project, command, capsys):
    root, _, _, source = project
    args = [command, "--spec", str(root / "planning/deck.json"), "--audio", str(root / "MISSING.wav.json"),
            "--out", str(root / "absent")]
    if command != "timeline":
        args += ["--timeline", str(root / "planning/authored.json")]
    if command == "render":
        args += ["--source", str(source)]
    assert cli.main(args) == 1
    assert "narrated" in capsys.readouterr().out
    assert not (root / "absent").exists()


@pytest.mark.parametrize("option", ["--audio", "--slides"])
def test_preview_cli_does_not_accept_narration_or_partial_selection(project, option):
    root, _, _, source = project
    with pytest.raises(SystemExit) as error:
        cli.main(["silent-preview", "--spec", str(root / "planning/deck.json"), "--authored-timeline",
            str(root / "planning/authored.json"), "--source", str(source), "--out", str(root / "absent"), option, "x"])
    assert error.value.code == 2


def test_partial_narrated_reuse_rejects_preview_manifest_before_any_write(narrated_project):
    root, out, spec, audio, timeline, manifest = narrated_project
    manifest.update(schema_version="research-preview-render-1", mode="silent-preview")
    path = out / "render-manifest.json"
    path.write_text(json.dumps(manifest))
    before = snapshot(out)
    with pytest.raises(ValueError, match="narrated"):
        cli.render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out,
                           profile="draft", root=root, slides=["s01"])
    assert snapshot(out) == before


def test_narrated_shared_kernel_preserves_explicit_final_profile_with_15fps_settings(narrated_project):
    root, _, spec, audio, _, _ = narrated_project
    spec["render"] = {"width": 960, "height": 540, "fps": 15}
    timeline = build_timeline(spec, audio, 15)
    result = cli.render_project(spec, audio, timeline, source=root / "src/scenes.py",
        out=root / "final-custom-settings", profile="final", root=root)
    assert result["profile"] == "final"
    assert result["schema_version"] == "research-render-1" and "mode" not in result
    assert result["settings"] == {"width": 960, "height": 540, "fps": 15}


@pytest.mark.parametrize("fault", ["valid", "late_declaration", "missing", "invalid", "inactive", "third", "trace_mismatch", "legacy"])
def test_retained_real_media_replays_math_contact_without_exempting_other_objects(tmp_path, fault):
    # Real ordinary-scene observations and MP4, not fabricated geometry or media.
    from manim import Circle, Line, tempconfig
    from research.scene import ResearchScene, ensure_font
    from research.themes import load_theme
    ensure_font()
    class ContactScene(ResearchScene):
        def construct(self):
            self.add(self.track("axis", Line([-2, 0, 0], [2, 0, 0], stroke_width=1), "shape"))
            output = self.track("output", Circle(radius=.08, stroke_width=1,
                fill_opacity=1).move_to([0, 1 if fault in {"legacy", "late_declaration"} else 0, 0]), "shape")
            self.add(output)
            if fault == "late_declaration":
                self.beat("before", [], 0)
                output.move_to([0, 0, 0])
            if fault != "legacy":
                self.math_contact("on-axis", kind="point_on_number_line", objects=("axis", "output"),
                                  start_frame=1 if fault == "late_declaration" else 0, end_frame=3)
            self.beat("hold", [], 0)
    spec = {"slides": [{"id": "s", "screen_text": {"title": "测量"}, "beats": [{"id": "hold"}]}]}
    timing = {"id": "s", "start_frame": 0, "end_frame": 3, "frames": 3, "beats": [
        {"id": "hold", "start_frame": 0, "end_frame": 3, "local_start_frame": 0,
         "local_end_frame": 3, "frames": 3}]}
    if fault == "late_declaration":
        timing["beats"][0].update(start_frame=1, local_start_frame=1, frames=2)
        timing["beats"].insert(0, {"id": "before", "start_frame": 0, "end_frame": 1,
            "local_start_frame": 0, "local_end_frame": 1, "frames": 1})
    timeline = {"schema_version": "research-timeline-1", "fps": 15, "timeline_hash": "contact-fixture",
                "slides": [timing]}
    settings = {"width": 960, "height": 540, "fps": 15}
    with tempconfig({"media_dir": str(tmp_path / "media"), "frame_rate": 15,
        "pixel_width": 960, "pixel_height": 540, "disable_caching": True,
        "save_last_frame": False, "write_to_movie": True, "verbosity": "ERROR", "progress_bar": "none"}):
        scene = ContactScene(spec=spec, timeline=timeline, slide_id="s", theme=load_theme("midnight"),
            audit_dir=tmp_path / "audit", output_folder=tmp_path / "slides")
        scene.skip_reversing = True
        scene.render()
    paths = {"master": Path(scene.renderer.file_writer.movie_file_path), "trace": tmp_path / "audit/frames.jsonl",
             "qa": tmp_path / "audit/qa.json", "slides_json": tmp_path / "slides/ContactScene.json"}
    qa = media.read_json(paths["qa"])
    trace = [json.loads(row) for row in paths["trace"].read_text().splitlines()]
    assert qa["ok"] is True and len(trace) == 3
    if fault == "missing":
        qa.pop("math_contacts")
    elif fault == "invalid":
        qa["math_contacts"][0]["kind"] = "arbitrary_overlap"
    elif fault == "inactive":
        qa["math_contacts"][0]["end_frame"] = 1
    elif fault == "trace_mismatch":
        trace[0]["math_contacts"] = []
    elif fault == "third":
        for row in trace:
            third = copy.deepcopy(next(obj for obj in row["objects"] if obj["id"] == "output"))
            third["id"] = "third"
            row["objects"].append(third)
    elif fault == "legacy":
        qa.pop("math_contacts")
        for row in trace:
            row.pop("math_contacts")
    paths["qa"].write_text(json.dumps(qa))
    paths["trace"].write_text("".join(json.dumps(row) + "\n" for row in trace))
    item = {"slide_id": "s", "start_frame": 0, "end_frame": 3, "frames": 3,
            **{key: str(path) for key, path in paths.items()},
            **{key + "_sha256": media.sha(path) for key, path in paths.items()}}
    if fault in {"valid", "late_declaration", "legacy"}:
        assert len(media.validate_render_slide(item, timing, settings)) == 3
    else:
        with pytest.raises(ValueError, match="geometry|contact"):
            media.validate_render_slide(item, timing, settings)

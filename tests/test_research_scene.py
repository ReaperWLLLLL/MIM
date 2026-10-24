"""Real Manim boundary tests: no mocked renderer/animation geometry."""
import importlib
import copy
import hashlib
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave
import weakref

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from manim import FadeIn, FadeOut, Rectangle, Text, Transform, VGroup, tempconfig
from research.themes import load_theme
from voice_fixture import bind_audio


@pytest.fixture(autouse=True)
def isolated_manim_media(tmp_path):
    with tempconfig({"media_dir": str(tmp_path / "manim-cache")}):
        yield


def api():
    try:
        return importlib.import_module("research.scene")
    except ModuleNotFoundError:
        pytest.fail("research.scene has not been implemented")


def make_scene(tmp_path, **kwargs):
    scene_api = api()
    scene_api.ensure_font()
    spec = {"slides": [{"id": "s1", "screen_text": {"a": "测量", "b": "比较"},
                         "beats": [{"id": "a"}], "notes": "讲者备注"}]}
    timeline = {"fps": 15, "timeline_hash": "fixture", "slides": [
        {"id": "s1", "start_frame": 0, "end_frame": 6, "frames": 6,
         "beats": [{"id": "a", "local_start_frame": 0, "local_end_frame": 6, "frames": 6}]}]}
    with tempconfig({"media_dir": str(tmp_path / "media"), "frame_rate": 15,
                     "pixel_width": 640, "pixel_height": 360, "disable_caching": True}):
        return scene_api.ResearchScene(spec=spec, timeline=timeline, slide_id="s1",
            theme=kwargs.pop("theme", load_theme("midnight")), audit_dir=tmp_path / "audit", output_folder=tmp_path / "slides", **kwargs)


def test_theme_font_roles_are_validated_and_isolated_per_scene(tmp_path):
    custom = make_scene(tmp_path / "custom", theme=load_theme("custom", {
        "font_sizes": {"title": 50, "body": 32, "caption": 22}}))
    default = make_scene(tmp_path / "default")
    assert custom.text("a").font_size == pytest.approx(32)
    assert default.text("a").font_size == pytest.approx(30)
    assert custom.layout["font_sizes"] == {"title": 50, "body": 32, "caption": 22}
    assert default.layout["font_sizes"] == {"title": 48, "body": 30, "caption": 20}
    non_role = custom.track("non-role", Text("比较", font="Microsoft YaHei", font_size=30), "text", role="body")
    custom.add(non_role)
    from research.layout import check_frame
    assert any(f["code"] == "font_size" for f in check_frame(custom.observed_objects(), 0, custom.layout))
    invalid = load_theme("midnight")
    invalid["font_sizes"]["body"] = 12
    with pytest.raises(ValueError, match="font_sizes"):
        make_scene(tmp_path / "invalid", theme=invalid)
    with pytest.raises(ValueError, match="layout"):
        make_scene(tmp_path / "override", theme=load_theme("custom", {
            "font_sizes": {"title": 50, "body": 32, "caption": 22}}),
            layout={"font_sizes": {"title": 48, "body": 30, "caption": 20}})


def test_group_registration_cannot_hide_independent_unregistered_text(tmp_path):
    scene = make_scene(tmp_path)
    hidden = Text("漏检", font="Microsoft YaHei", font_size=30)
    group = scene.track("group", VGroup(hidden), "group")
    scene.add(group)
    records = scene.observed_objects()
    assert any(r["kind"] == "text" and not r["registered"] for r in records)


def test_shape_parent_cannot_hide_unregistered_shape_or_expand_its_own_boundary(tmp_path):
    from manim import Circle
    scene = make_scene(tmp_path)
    box = scene.track("box", Rectangle(width=2, height=2), "container")
    box.set_opacity(0)
    child = Circle(radius=.5).shift([3, 0, 0])
    box.add(child)
    scene.add(box)
    records = scene.observed_objects()
    assert any(not record["registered"] for record in records)
    assert next(r["bbox"] for r in records if r["id"] == "box") == [-1, -1, 1, 1]
    assert next(r["visible"] for r in records if r["id"] == "box") is False


@pytest.mark.parametrize("attachment", ["text", "glyph", "before_track"])
def test_text_child_shape_is_observed_without_registering_genuine_glyphs(tmp_path, attachment):
    from manim import Circle
    from research.layout import check_frame
    scene = make_scene(tmp_path)
    text = (Text("测量", font="Microsoft YaHei", font_size=30)
            if attachment == "before_track" else scene.text("a"))
    child = Circle(radius=.03, fill_opacity=1).move_to(text)
    (text.chars[0] if attachment == "glyph" else text).add(child)
    if attachment == "before_track":
        scene.track("text:a", text, "text", role="body")
    scene.add(text)
    records = scene.observed_objects()
    assert len(records) == 2  # the Text and independent shape, not its glyph paths
    text_record = next(r for r in records if r["kind"] == "text")
    assert text_record["effective_font_size"] == pytest.approx(30)
    findings = check_frame(records, 0, {})
    assert any(f["code"] == "unregistered" for f in findings)


def test_text_glyph_size_cannot_borrow_height_from_a_registered_child(tmp_path):
    from research.layout import check_frame
    scene = make_scene(tmp_path)
    text = scene.text("a")
    original_height = text.height
    text.scale(.5)
    marker = scene.track("marker", Rectangle(width=.03, height=original_height), "shape")
    text.add(marker)
    scene.add(text)
    records = scene.observed_objects()
    text_record = next(r for r in records if r["kind"] == "text")
    assert text_record["effective_font_size"] == pytest.approx(15)
    assert text_record["bbox"][3] - text_record["bbox"][1] == pytest.approx(original_height / 2)
    assert any(f["code"] == "font_size" for f in check_frame(records, 0, {}))


def test_visible_child_does_not_make_transparent_glyphs_visible(tmp_path):
    from manim import Circle
    scene = make_scene(tmp_path)
    text = scene.text("a").set_opacity(0)
    text.add(Circle(radius=.03, fill_opacity=1).move_to(text))
    scene.add(text)
    records = scene.observed_objects()
    assert next(r["visible"] for r in records if r["kind"] == "text") is False
    assert any(r["visible"] and not r["registered"] for r in records)


def test_registered_identity_is_retained_so_python_id_reuse_cannot_register_a_stranger(tmp_path):
    scene = make_scene(tmp_path)
    shape = scene.track("retained", Rectangle(), "shape")
    reference = weakref.ref(shape)
    del shape
    gc.collect()
    assert reference() is not None


@pytest.mark.parametrize("animation", ["fade_in", "fade_out", "transform_target"])
def test_animation_preflight_detects_unregistered_foreground(tmp_path, animation):
    scene = make_scene(tmp_path)
    source = scene.text("a")
    loose = Text("比较", font="Microsoft YaHei", font_size=30)
    anim = {"fade_in": lambda: FadeIn(loose), "fade_out": lambda: FadeOut(loose),
            "transform_target": lambda: Transform(source, loose)}[animation]()
    findings = scene.check_animations([anim])
    assert any(f["code"] == "unregistered" for f in findings)


def test_scaled_group_reports_effective_text_size_not_declared_size(tmp_path):
    scene = make_scene(tmp_path)
    text = scene.text("a")
    scene.add(VGroup(text).scale(.5))
    record = next(r for r in scene.observed_objects() if r["kind"] == "text")
    assert record["effective_font_size"] == pytest.approx(15)
    from research.layout import check_frame
    assert any(f["code"] == "font_size" for f in check_frame([record], 0, {}))


def test_fadein_text_visibility_uses_painted_glyph_opacity(tmp_path):
    scene = make_scene(tmp_path)
    text = scene.text("a")
    animation = FadeIn(text)
    assert scene.check_animations([animation]) == []
    scene.add(text)
    animation.begin()
    animation.interpolate(0)
    assert scene.observed_objects()[0]["visible"] is False


def test_registered_copy_animation_keeps_identity_but_text_transform_is_conservative(tmp_path):
    scene = make_scene(tmp_path)
    source = scene.text("a")
    assert scene.check_animations([source.animate.shift([1, 0, 0])]) == []
    assert any(f["code"] == "text_transform" for f in scene.check_animations([Transform(source, scene.text("b"))]))


@pytest.mark.parametrize("copy", ["Input and output", "测量\n结果"])
def test_exact_source_copy_with_whitespace_is_audited_and_can_move(tmp_path, copy):
    # Reading Manim's glyph-index text instead of its source loses this copy.
    scene = make_scene(tmp_path)
    scene.slide_spec["screen_text"]["a"] = copy
    label = scene.text("a")
    scene.add(label)
    records = scene.observed_objects()
    assert records[0]["text"] == copy
    assert scene._copy_findings(records) == []
    assert scene.check_animations([FadeIn(label), label.animate.shift([1, 0, 0])]) == []


@pytest.mark.parametrize("canonical,displayed", [
    ("A B C", "ABC"), ("A B C", "AB C"), ("A B C", "A BC"),
    ("A B C", "A B D"), ("A B C", "A\nB C"), ("测量\n结果", "测量结果"),
])
def test_registered_near_match_cannot_replace_exact_source_copy(tmp_path, canonical, displayed):
    # Removing whitespace before comparing, or trusting registration, misses these.
    scene = make_scene(tmp_path)
    scene.slide_spec["screen_text"]["a"] = canonical
    label = scene.track("text:a", Text(displayed, font="Microsoft YaHei", font_size=30),
                        "text", role="body")
    scene.add(label)
    records = scene.observed_objects()
    assert records[0]["text"] == displayed
    assert any(f["code"] == "screen_text" for f in scene._copy_findings(records))


@pytest.mark.parametrize("source,target", [("A B", "AB"), ("测量\n结果", "测量结果")])
def test_transform_rejects_whitespace_only_source_change(tmp_path, source, target):
    # Both copies are allowed separately; a text-changing glyph morph is not.
    scene = make_scene(tmp_path)
    scene.slide_spec["screen_text"].update(a=source, b=target)
    findings = scene.check_animations([Transform(scene.text("a"), scene.text("b"))])
    assert any(f["code"] == "text_transform" for f in findings)


def test_text_helper_rejects_font_override_and_unregistered_copy(tmp_path):
    scene = make_scene(tmp_path)
    with pytest.raises(ValueError, match="font"):
        scene.text("a", font_size=15)
    with pytest.raises(ValueError, match="screen_text"):
        scene.text("missing")
    with pytest.raises(ValueError, match="role"):
        scene.text("a", role="tiny")


@pytest.mark.parametrize("layout", [{"font_sizes": {"title": 36, "body": 24, "caption": 18}},
                                   {"viewport": [-100, -100, 100, 100]}])
def test_audit_config_cannot_weaken_fixed_font_roles_or_lie_about_viewport(tmp_path, layout):
    with pytest.raises(ValueError, match="layout"):
        make_scene(tmp_path, layout=layout)


def test_connector_has_actual_tip_geometry_and_explicit_endpoint_ids(tmp_path):
    from manim import Arrow
    scene = make_scene(tmp_path)
    left = scene.track("left", Rectangle(width=2, height=1).shift([-3, 0, 0]), "container")
    right = scene.track("right", Rectangle(width=2, height=1).shift([3, 0, 0]), "container")
    arrow = scene.track("link", Arrow(left.get_right(), right.get_left(), buff=0, tip_length=.2),
                        "connector", endpoints=("left", "right"))
    scene.add(left, right, arrow)
    records = scene.observed_objects()
    connector = next(r for r in records if r["id"] == "link")
    assert len(connector["tips"]) == 1
    assert connector["endpoints"][1]["point"] == pytest.approx([2, 0])
    from research.layout import check_frame
    assert check_frame(records, 0, {}) == []


def test_paint_bounds_observe_cairo_miter_square_caps_and_camera_scale(tmp_path):
    from manim import VMobject, Line, CapStyleType, LineJointType
    scene = make_scene(tmp_path)
    corner = scene.track("corner", VMobject(stroke_width=20, joint_type=LineJointType.MITER)
        .set_points_as_corners([[-1, 0, 0], [0, 0, 0], [-1, .3, 0]]), "shape")
    line = scene.track("line", Line([1, 1, 0], [2, 2, 0], stroke_width=20,
                                   cap_style=CapStyleType.SQUARE), "shape")
    scene.add(corner, line)
    scene.camera.capture_mobjects(scene.mobjects)
    first = {r["id"]: r for r in scene.observed_objects()}
    assert first["corner"]["bbox"][2] > .6  # a half-width-only formula misses this join
    assert first["line"]["bbox"][0] < .87  # diagonal square cap exceeds radius=.1
    scene.camera.frame_width *= 2
    scene.camera.capture_mobjects(scene.mobjects)
    second = {r["id"]: r for r in scene.observed_objects()}
    assert second["line"]["paint_radius"] == pytest.approx(first["line"]["paint_radius"], abs=.001)


@pytest.mark.parametrize("fault,code", [("border", "collision"), ("line_text", "collision"),
    ("edge", "safe_boundary"), ("padding", "container_overflow"),
    ("animated", "collision"), ("background", "collision")])
def test_real_render_audits_actual_stroke_paint(render_project, fault, code):
    root, project = render_project
    setups = {
        "border": 'a = self.track("a", Rectangle(width=1, height=1, stroke_width=100), "shape")\nb = self.track("b", Rectangle(width=1, height=1, stroke_width=100).shift([1.15,0,0]), "shape")',
        "line_text": 'a = self.track("a", Line([-2,0,0],[2,0,0], stroke_width=100), "shape")\nb = self.text("title", role="title").next_to(a, UP, buff=.15)',
        "edge": 'a = self.track("a", Rectangle(width=1, height=1, stroke_width=100).shift([5.8,0,0]), "shape")\nb = self.track("b", Rectangle(width=1, height=1).shift([-2,0,0]), "shape")',
        "padding": 'a = self.track("a", Rectangle(width=2, height=2, stroke_width=100), "container")\nb = self.track("b", Rectangle(width=1.5, height=1, stroke_width=0, fill_opacity=1), "shape", parent="a")',
        "animated": 'a = self.track("a", Rectangle(width=1, height=1, stroke_width=2), "shape")\nb = self.track("b", Rectangle(width=1, height=1, stroke_width=2).shift([1.3,0,0]), "shape")',
        "background": 'a = self.track("a", Rectangle(width=1, height=1, stroke_width=0, fill_opacity=0).set_stroke(width=100, opacity=1, background=True), "shape")\nb = self.track("b", Rectangle(width=1, height=1, stroke_width=0, fill_opacity=0).set_stroke(width=100, opacity=1, background=True).shift([1.15,0,0]), "shape")',
    }
    animation = '[a.animate.set_stroke(width=100)]' if fault == "animated" else '[]'
    body = setups[fault] + '\nself.add(a,b)\nself.beat("observe", ' + animation + ', .2)\nself.beat("compare", [], 0)'
    (project / "src/scenes.py").write_text('from manim import Rectangle, Line, UP\nfrom research.scene import ResearchScene\nclass Example(ResearchScene):\n    def construct(self):\n' + ''.join('        '+line+'\n' for line in body.splitlines()))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode != 0, "paint overlap incorrectly admitted"
    qa = json.loads((project / "rendered/slide-0000/audit/qa.json").read_text())
    assert any(f["code"] == code for f in qa["findings"]), qa
    if fault == "animated":
        frames = [json.loads(line) for line in (project / "rendered/slide-0000/audit/frames.jsonl").read_text().splitlines()]
        assert not frames[0]["findings"]
        assert any(f["findings"] for f in frames[1:])


def test_profile_resolution_keeps_16_by_9_and_final_default_60_fps():
    try:
        cli = importlib.import_module("build_research")
    except ModuleNotFoundError:
        pytest.fail("build_research has not been implemented")
    assert cli.profile_settings({}, "final") == {"width": 1920, "height": 1080, "fps": 60}
    draft = cli.profile_settings({}, "draft")
    assert draft["width"] * 9 == draft["height"] * 16
    assert draft["fps"] == 15


@pytest.fixture
def render_project(tmp_path, request):
    root = Path(__file__).resolve().parents[1]
    template = root / "assets/research-template"
    assert template.is_dir(), "research-template has not been implemented"
    project = tmp_path / getattr(request, "param", "project")
    shutil.copytree(template, project)
    import yaml
    from research.spec import content_hash
    spec = yaml.safe_load((project / "planning/deck.yaml").read_text())
    audio = {"job_id": "fixture-only-no-tts", "settings": {}, "audio": []}
    for i, beat in enumerate(spec["slides"][0]["beats"]):
        path = project / f"beat-{i}.wav"
        with wave.open(str(path), "wb") as out:
            out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            out.writeframes(b"\x01\x00" * 9600)
        audio["audio"].append({"slide_id": "s01", "beat_id": beat["id"], "path": str(path),
            "sample_count": 9600, "sample_rate": 24000,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "narration": beat["narration"], "spoken_text": beat["narration"],
            "text_hash": content_hash(beat["narration"]), "narration_hash": content_hash(beat["narration"])})
    bind_audio(spec, audio)
    (project / "audio.json").write_text(json.dumps(audio, ensure_ascii=False))
    return root, project


def cli_run(root, project, *args):
    env = dict(os.environ)
    # Developer workstation has a broken /opt/homebrew/bin/ffmpeg. Scope the
    # working installation to this child; production uses the caller's PATH.
    ffmpeg_dir = "/opt/homebrew/Caskroom/miniconda/base/envs/manim/bin"
    if Path(ffmpeg_dir, "ffmpeg").is_file():
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + ffmpeg_dir + os.pathsep + env["PATH"]
    return subprocess.run([sys.executable, str(root / "scripts/build_research.py"), *args],
        cwd=project, env=env, text=True, capture_output=True, timeout=120)


@pytest.mark.parametrize("render_project", ["中文 O'Brien 空格\\token\nline"], indirect=True)
def test_real_partial_concat_handles_special_project_path(render_project):
    root, project = render_project
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 0, result.stdout + result.stderr
    from research.media import _video
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    assert manifest["slides"][0]["frames"] == 12
    _video(manifest["slides"][0]["master"], {"frames": 12}, manifest["settings"])


def freeze(root, project, profile="draft"):
    result = cli_run(root, project, "timeline", "--spec", "planning/deck.yaml", "--audio", "audio.json",
                     "--out", "timeline.json", "--profile", profile)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("theme", ["midnight", "paper", "slate", "custom"])
def test_real_render_all_frames_match_silent_master_and_preserve_slide_notes(render_project, theme):
    root, project = render_project
    freeze(root, project)
    extra = ["--theme-file", "planning/custom-theme.yaml"] if theme == "custom" else []
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft", "--theme", theme, *extra)
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    assert manifest["ok"] is True
    slide = manifest["slides"][0]
    assert slide["observed_frames"] == slide["frames"] == 12
    assert slide["fps"] == 15
    assert slide["has_audio"] is False
    trace = [json.loads(line) for line in Path(slide["trace"]).read_text().splitlines()]
    assert [r["local_frame"] for r in trace] == list(range(12))
    assert not [f for frame in trace for f in frame["findings"]]
    assert any(r["kind"] == "connector" for frame in trace for r in frame["objects"])
    qa = json.loads(Path(slide["qa"]).read_text())
    assert all(b["wait_frames"] > 0 for b in qa["beats"])
    native = json.loads(Path(slide["slides_json"]).read_text())
    assert native["slides"][0]["notes"]


def test_real_render_keeps_english_spaces_and_chinese_newlines_in_audit(render_project):
    # The renderer must audit actual Text source, not reject it or rewrite evidence.
    root, project = render_project
    import yaml
    path = project / "planning/deck.yaml"
    spec = yaml.safe_load(path.read_text())
    spec["slides"][0]["screen_text"].update(title="Input and output", caption="测量\n结果")
    path.write_text(yaml.safe_dump(spec, allow_unicode=True))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    assert manifest["ok"] is True
    slide = manifest["slides"][0]
    trace = [json.loads(line) for line in Path(slide["trace"]).read_text().splitlines()]
    assert len(trace) == slide["observed_frames"] == slide["frames"] == 12
    assert not [f for frame in trace for f in frame["findings"]]
    for frame in trace:
        texts = {r["id"]: r["text"] for r in frame["objects"] if r["kind"] == "text"}
        assert texts["text:title"] == "Input and output"
        assert texts["text:caption"] == "测量\n结果"


def test_real_render_keeps_exact_cadence_across_eleven_frame_partial(render_project):
    # Manim's 11-frame MP4 header is short by five track ticks; concatenating
    # by that duration moves the following audited hold off its frame boundary.
    root, project = render_project
    audio_path = project / "audio.json"
    audio = json.loads(audio_path.read_text())
    cue = audio["audio"][0]
    with wave.open(cue["path"], "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(b"\x01\x00" * 24000)
    cue.update(sample_count=24000, sha256=hashlib.sha256(Path(cue["path"]).read_bytes()).hexdigest())
    audio_path.write_text(json.dumps(audio, ensure_ascii=False))
    source = project / "src/scenes.py"
    source.write_text(source.read_text().replace("output_label, link)], .2)", "output_label, link)], .7)"))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    slide = manifest["slides"][0]
    assert slide["observed_frames"] == slide["frames"] == 21
    from research.media import validate_render_slide
    timing = json.loads((project / "timeline.json").read_text())["slides"][0]
    assert len(validate_render_slide(slide, timing, manifest["settings"])) == 21
    from research.media import frame_hashes
    partials = sorted(Path(slide["master"]).parent.rglob("uncached_*.mp4"))
    assert partials
    assert frame_hashes(slide["master"]) == [h for path in partials for h in frame_hashes(path)]


def test_real_render_preserves_619_frames_and_exact_partial_seams(render_project):
    # Reproduce the observed 243/200/176-frame beats without the producer's copy.
    root, project = render_project
    import yaml
    from research.spec import content_hash
    path = project / "planning/deck.yaml"
    spec = yaml.safe_load(path.read_text())
    third = copy.deepcopy(spec["slides"][0]["beats"][1])
    third.update(id="hold", narration="保持测量条件。")
    spec["slides"][0]["beats"].append(third)
    path.write_text(yaml.safe_dump(spec, allow_unicode=True))
    audio = {"job_id": "fixture-only-no-tts", "settings": {}, "audio": []}
    for beat, frames in zip(spec["slides"][0]["beats"], [243, 200, 176]):
        wav = project / f"{beat['id']}.wav"
        with wave.open(str(wav), "wb") as out:
            out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            out.writeframes(b"\x01\x00" * (frames * 1600))
        audio["audio"].append({"slide_id": "s01", "beat_id": beat["id"], "path": str(wav),
            "sample_count": frames * 1600, "sample_rate": 24000,
            "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
            "narration": beat["narration"], "spoken_text": beat["narration"],
            "text_hash": content_hash(beat["narration"]), "narration_hash": content_hash(beat["narration"])})
    bind_audio(spec, audio)
    (project / "audio.json").write_text(json.dumps(audio, ensure_ascii=False))
    (project / "src/scenes.py").write_text('''from research.scene import ResearchScene
class Example(ResearchScene):
    def construct(self):
        label = self.text("title", role="title")
        self.add(label)
        self.beat("observe", [label.animate.shift([.1, 0, 0])], 1.2)
        self.beat("compare", [label.animate.shift([.1, 0, 0])], .8)
        self.beat("hold", [label.animate.shift([.1, 0, 0])], .7)
''')
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    slide = manifest["slides"][0]
    assert slide["observed_frames"] == slide["frames"] == 619
    from research.media import frame_hashes, validate_render_slide
    timing = json.loads((project / "timeline.json").read_text())["slides"][0]
    assert len(validate_render_slide(slide, timing, manifest["settings"])) == 619
    partials = sorted(Path(slide["master"]).parent.rglob("uncached_*.mp4"))
    assert len(partials) == 6
    assert frame_hashes(slide["master"]) == [h for path in partials for h in frame_hashes(path)]


@pytest.mark.parametrize("fault", ["rate", "cadence"])
def test_render_rejects_actual_wrong_rate_or_irregular_cadence(render_project, fault):
    # Native acceptance must check actual PTS, not only count and average FPS.
    root, project = render_project
    expression = "setpts=" + ("N/(14*TB)" if fault == "rate" else "PTS+if(eq(N\\,5)\\,0.02/TB\\,0)")
    source = project / "src/scenes.py"
    source.write_text(source.read_text() + '''
    def render(self, *args, **kwargs):
        super().render(*args, **kwargs)
        from pathlib import Path
        from research.media import ffmpeg
        path = Path(self.renderer.file_writer.movie_file_path)
        changed = path.with_name("changed.mp4")
        ffmpeg("-i", path, "-vf", EXPRESSION, "-fps_mode", "passthrough",
               "-enc_time_base", "1:15360", "-c:v", "libx264", changed)
        changed.replace(path)
'''.replace("EXPRESSION", repr(expression)))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert "ffmpeg failed" not in result.stdout, result.stdout + result.stderr
    from research.media import probe
    master = next((project / "rendered").rglob("silent-master.mp4"))
    video = next(s for s in probe(master)["streams"] if s["codec_type"] == "video")
    assert int(video["nb_read_frames"]) == 12
    if fault == "cadence":
        assert video["avg_frame_rate"] == "15/1"  # A metadata-only check would pass.
    assert result.returncode == 1, result.stdout + result.stderr
    assert "video frame" in result.stdout or "master media" in result.stdout
    assert json.loads((project / "rendered/render-manifest.json").read_text())["ok"] is False


@pytest.mark.parametrize("fault,code", [("fadein", "unregistered"), ("fadeout", "unregistered"),
    ("transform", "unregistered"), ("direct_transform", "unregistered"),
    ("scaled", "font_size"), ("motion", "safe_boundary"), ("collision", "collision"),
    ("group", "unregistered"), ("text_child", "unregistered")])
def test_real_failure_render_exits_nonzero_with_frame_evidence(render_project, fault, code):
    root, project = render_project
    source = '''from manim import *
from research.scene import ResearchScene
class Example(ResearchScene):
    def construct(self):
        label = self.text("title", role="title").move_to([0, 2, 0])
        loose = Text("测量流程", font="Microsoft YaHei", font_size=48).move_to([0, 2, 0])
        fault = FAULT
        if fault == "fadein":
            animations = [FadeIn(loose)]
        elif fault == "fadeout":
            self.add(loose)
            animations = [FadeOut(loose)]
        elif fault == "transform":
            self.add(label)
            animations = [Transform(label, loose)]
        elif fault == "direct_transform":
            self.add(label)
            self.play(Transform(label, loose), run_time=.2)
            animations = []
        elif fault == "scaled":
            self.add(VGroup(label).scale(.5))
            animations = []
        elif fault == "motion":
            self.add(label)
            animations = [label.animate.shift(RIGHT * 10)]
        elif fault == "collision":
            label.move_to([-3, 2, 0])
            block = self.track("block", Rectangle(width=.6, height=.6).move_to([0, 2, 0]), "shape")
            self.add(label, block)
            animations = [label.animate.shift(RIGHT * 6)]
        elif fault == "text_child":
            label.add(Circle(radius=.03, fill_opacity=1).move_to(label))
            self.add(label)
            animations = []
        else:
            self.add(self.track("group", VGroup(loose), "group"))
            animations = []
        self.beat("observe", animations, .4 if fault == "collision" else .2)
        self.beat("compare", [], 0)
'''.replace("FAULT", repr(fault))
    (project / "src/scenes.py").write_text(source)
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 1, result.stdout + result.stderr
    qa_files = list((project / "rendered").rglob("qa.json"))
    assert qa_files
    qa = json.loads(qa_files[0].read_text())
    assert any(f["code"] == code and isinstance(f["frame"], int) for f in qa["findings"])
    assert list(qa_files[0].parent.glob("failure-frame-*.png"))
    assert json.loads((project / "rendered/render-manifest.json").read_text())["ok"] is False
    if fault == "collision":
        trace = [json.loads(line) for line in (qa_files[0].parent / "frames.jsonl").read_text().splitlines()]
        assert not trace[0]["findings"] and not trace[-1]["findings"]


def test_final_profile_renders_actual_1080p60_and_has_every_hold_frame(render_project):
    root, project = render_project
    freeze(root, project, "final")
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered")
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    slide = manifest["slides"][0]
    assert (slide["width"], slide["height"], slide["fps"], slide["observed_frames"]) == (1920, 1080, 60, 48)
    trace = [json.loads(line) for line in Path(slide["trace"]).read_text().splitlines()]
    assert len(trace) == 48
    assert trace[36]["objects"] == trace[47]["objects"]
    assert {r["role"]: round(r["effective_font_size"]) for r in trace[-1]["objects"] if r["kind"] == "text"} == {"title": 48, "body": 30, "caption": 20}


@pytest.mark.parametrize("scaled", [None, "text", "group"])
def test_custom_role_group_renders_observed_sizes_but_rejects_scaling(render_project, scaled):
    root, project = render_project
    import yaml
    path = project / "planning/custom-theme.yaml"
    theme = yaml.safe_load(path.read_text())
    theme["font_sizes"] = {"title": 50, "body": 32, "caption": 22}
    path.write_text(yaml.safe_dump(theme))
    if scaled:
        source = project / "src/scenes.py"
        replacement = ('title.scale(.5)' if scaled == "text" else
                       '__import__("manim").VGroup(title).scale(.5)')
        source.write_text(source.read_text().replace("self.add(title, caption)",
            replacement + "\n        self.add(title, caption)"))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft",
        "--theme", "custom", "--theme-file", "planning/custom-theme.yaml")
    if scaled:
        assert result.returncode == 1, result.stdout + result.stderr
        qa_files = list((project / "rendered").rglob("qa.json"))
        assert qa_files, result.stdout + result.stderr
        qa = json.loads(qa_files[0].read_text())
        assert any(f["code"] == "font_size" for f in qa["findings"])
        assert list(qa_files[0].parent.glob("failure-frame-*.png"))
        return
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((project / "rendered/render-manifest.json").read_text())
    assert manifest["ok"] is True
    slide = manifest["slides"][0]
    trace = [json.loads(line) for line in Path(slide["trace"]).read_text().splitlines()]
    assert len(trace) == slide["observed_frames"] == slide["frames"] == 12
    assert not [f for frame in trace for f in frame["findings"]]
    sizes = {r["role"]: r["effective_font_size"] for r in trace[-1]["objects"] if r["kind"] == "text"}
    assert sizes == pytest.approx({"title": 50, "body": 32, "caption": 22})
    from research.media import frame_hashes
    assert len(frame_hashes(slide["master"])) == 12


def test_two_logical_slides_keep_global_frames_and_separate_native_metadata(render_project):
    root, project = render_project
    import yaml
    path = project / "planning/deck.yaml"
    spec = yaml.safe_load(path.read_text())
    second = copy.deepcopy(spec["slides"][0]); second["id"] = "s02"
    second["scene_class"] = "Second"
    spec["slides"].append(second)
    spec["project"]["duration_minutes"] = .4
    path.write_text(yaml.safe_dump(spec, allow_unicode=True))
    source = project / "src/scenes.py"
    source.write_text(source.read_text() + "\nclass Second(Example):\n    pass\n")
    audio_path = project / "audio.json"
    audio = json.loads(audio_path.read_text())
    second_audio = copy.deepcopy(audio["audio"])
    for item in second_audio:
        item["slide_id"] = "s02"
    audio["audio"].extend(second_audio)
    bind_audio(spec, audio)
    audio_path.write_text(json.dumps(audio, ensure_ascii=False))
    freeze(root, project)
    result = cli_run(root, project, "render", "--spec", "planning/deck.yaml", "--audio", "audio.json",
        "--timeline", "timeline.json", "--source", "src/scenes.py", "--out", "rendered", "--profile", "draft")
    assert result.returncode == 0, result.stdout + result.stderr
    slides = json.loads((project / "rendered/render-manifest.json").read_text())["slides"]
    assert len(slides) == 2
    assert slides[0]["slides_json"] != slides[1]["slides_json"]
    trace = [json.loads(line) for line in Path(slides[1]["trace"]).read_text().splitlines()]
    assert [(r["frame"], r["local_frame"]) for r in trace] == list(zip(range(12, 24), range(12)))


def test_voice_cli_timeout_reports_resumable_job_without_fake_audio(render_project, monkeypatch, capsys):
    root, project = render_project
    cli = importlib.import_module("build_research")
    from research import voice
    def pending(spec, root):
        raise voice.VoiceObservationTimeout("known-persistent-job")
    monkeypatch.setattr(voice, "synthesize_remote", pending)
    output = project / "new-audio.json"
    assert cli.main(["voice", "--spec", str(project / "planning/deck.yaml"), "--out", str(output)]) == 2
    assert not output.exists()
    result = json.loads(capsys.readouterr().out)
    assert result["pending"] is True and result["job_id"] == "known-persistent-job"

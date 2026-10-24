"""Real tiny videos: state, moving pixels and literal numeric glyphs agree."""
import importlib
import json

import av
import numpy as np
import pytest
from manim import Circle, Line, Text, Transform, tempconfig
from manim.camera.camera import Camera

from research.scene import AuditFailure, FONT, ResearchScene, _AuditedRenderer, ensure_font
from research.themes import load_theme


def preview_class():
    try:
        return importlib.import_module("research.preview_scene").SilentPreviewScene
    except ModuleNotFoundError:
        pytest.fail("SilentPreviewScene is missing")


@pytest.fixture
def configured(tmp_path):
    ensure_font()
    with tempconfig({"media_dir": str(tmp_path / "media"), "frame_rate": 15,
                     "pixel_width": 960, "pixel_height": 540, "disable_caching": True,
                     "save_last_frame": False, "write_to_movie": True,
                     "progress_bar": "none", "verbosity": "ERROR"}):
        yield


def make_scene(tmp_path, *, hold=False, fault=None, state=None):
    base = preview_class()

    class TinyPreview(base):
        def state_at(self, local_frame):
            if state is not None:
                return state
            frame = min(local_frame, 2) if hold else local_frame
            return {"x": frame, "value": [1.235, 2.345, 3.335, 4.995][frame]}

        def update_geometry(self, state):
            if hasattr(self, "dot"):
                self.dot.move_to([state["x"] - 1.5, -1, 0])

        def construct(self):
            self.dot = self.track("dot", Circle(radius=.08, color="#FF0000",
                fill_opacity=1, stroke_width=0), "shape")
            axis = self.track("axis", Line([-3, -1, 0], [3, -1, 0],
                color="#0000FF", stroke_width=2), "shape")
            self.label = self.derived_number("number", source="value", domain=(0, 6),
                position=(0, 2, 0))
            self.add(axis, self.dot, self.label)
            self.math_contact("on-axis", kind="point_on_number_line", objects=("axis", "dot"),
                start_frame=0, end_frame=4)
            if fault == "display":
                self.label.original_text = "9.99"
            elif fault == "scale":
                self.label.scale(.5)
            elif fault == "font":
                self.label.font = "Arial"
            elif fault == "child":
                self.label.add(Circle(radius=.02, fill_opacity=1).move_to([2, 2, 0]))
            elif fault == "ordinary":
                self.add(self.track("derived:impostor", Text("9.99", font=FONT,
                    font_size=30).move_to([3, 2, 0]), "text", role="body"))
            for beat in ("start", "move", "hold"):
                self.preview_beat(beat)

    beats = [{"id": key, "local_start_frame": start, "local_end_frame": end,
              "start_frame": start, "end_frame": end, "frames": end-start}
             for key, start, end in [("start", 0, 1), ("move", 1, 3), ("hold", 3, 4)]]
    scene = TinyPreview(spec={"slides": [{"id": "s", "screen_text": {"title": "测量"}}]},
        timeline={"schema_version": "research-preview-timeline-1", "mode": "silent-preview",
                  "fps": 15, "timeline_hash": "tiny", "slides": [
                      {"id": "s", "start_frame": 0, "end_frame": 4, "frames": 4, "beats": beats}]},
        slide_id="s", theme=load_theme("custom", {"colors": {
            "background": "#000000", "foreground": "#FFFFFF"}}),
        audit_dir=tmp_path / "audit", output_folder=tmp_path / "slides")
    scene.skip_reversing = True
    return scene


def white_mask(pixels):
    return np.min(pixels[:, :, :3], axis=2) > 150


@pytest.mark.parametrize("hold,positions,literals", [
    (False, [0, 1, 2, 3], ["1.24", "2.34", "3.34", "5.00"]),
    (True, [0, 1, 2, 2], ["1.24", "2.34", "3.34", "3.34"]),
])
def test_real_four_frames_pixels_state_glyphs_boundaries_and_final_hold(
        tmp_path, configured, hold, positions, literals):
    # Moving refresh to add_frame, caching static objects or frozen Wait breaks
    # these independently-rasterized literal glyph masks and red-dot centers.
    scene = make_scene(tmp_path, hold=hold)
    scene.render()
    trace = [json.loads(row) for row in (tmp_path / "audit/frames.jsonl").read_text().splitlines()]
    with av.open(scene.renderer.file_writer.movie_file_path) as clip:
        assert not clip.streams.audio
        decoded = [frame.to_ndarray(format="rgb24") for frame in clip.decode(video=0)]
    assert len(decoded) == 4
    assert [row["local_frame"] for row in trace] == [0, 1, 2, 3]
    assert [row["frame"] for row in trace] == [0, 1, 2, 3]
    assert [row["math_state"]["x"] for row in trace] == positions
    assert all(not row["findings"] for row in trace)
    assert [(b["start_frame"], b["end_frame"]) for b in scene._beat_log] == [(0, 1), (1, 3), (3, 4)]
    assert all(b["wait_frames"] == 0 for b in scene._beat_log)
    for pixels, row, x, literal in zip(decoded, trace, positions, literals):
        objects = {obj["id"]: obj for obj in row["objects"]}
        assert objects["dot"]["geometry"]["center"] == pytest.approx([x-1.5, -1])
        red = (pixels[:, :, 0] > 140) & (pixels[:, :, 1] < 75) & (pixels[:, :, 2] < 75)
        ys, xs = np.nonzero(red)
        assert len(xs) > 20
        assert np.mean(xs) == pytest.approx((x-1.5 + 64/9) * 960/(128/9), abs=1)
        assert np.mean(ys) == pytest.approx(337.5, abs=1)
        expected_label = Text(literal, font=FONT, font_size=30, color="#FFFFFF").move_to([0, 2, 0])
        camera = Camera(background_color="#000000")
        camera.capture_mobjects([expected_label])
        expected = white_mask(camera.pixel_array)
        observed = white_mask(pixels)
        # Region-specific visible glyph evidence, not whole-image change.
        observed[200:, :] = False
        union = np.count_nonzero(observed | expected)
        assert np.count_nonzero(observed & expected) / union > .94
        number = objects["number"]["derived_number"]
        assert number["source"] == "value"
        assert number["display"] == literal
        assert number["unrounded"] == row["math_state"]["value"]
        assert number["decimals"] == 2 and number["domain"] == [0, 6]
        assert abs(float(literal) - number["unrounded"]) <= .005000000001
        assert number["glyph_geometry"]
        assert objects["number"]["effective_font_size"] == pytest.approx(30)
    assert json.loads((tmp_path / "audit/qa.json").read_text())["ok"] is True


@pytest.mark.parametrize("options,state,match", [
    ({"source": "value + 1"}, {"value": 1}, "source"),
    ({"source": "missing"}, {"value": 1}, "source"),
    ({}, {"value": float("nan")}, "finite"),
    ({}, {"value": float("inf")}, "finite"),
    ({}, {"value": True}, "finite"),
    ({}, {"value": 7}, "domain"),
    ({"domain": (2, 1)}, {"value": 1}, "domain"),
    ({"domain": (0, float("inf"))}, {"value": 1}, "domain"),
    ({"decimals": 1}, {"value": 1}, "decimals"),
    ({"decimals": True}, {"value": 1}, "decimals"),
    ({"role": "tiny"}, {"value": 1}, "role"),
])
def test_derived_number_rejects_invalid_source_value_domain_precision(
        tmp_path, configured, options, state, match):
    scene = make_scene(tmp_path, state=state)
    args = {"source": "value", "domain": (0, 6), "position": (0, 2, 0), **options}
    with pytest.raises(ValueError, match=match):
        scene.derived_number("number", **args)


@pytest.mark.parametrize("fault,code", [("display", "screen_text"), ("scale", "font_size"),
    ("font", "font_family"), ("child", "unregistered"), ("ordinary", "screen_text")])
def test_derived_refresh_does_not_erase_text_font_scale_or_child_violations(
        tmp_path, configured, fault, code):
    scene = make_scene(tmp_path, fault=fault)
    with pytest.raises(AuditFailure):
        scene.render()
    qa = json.loads((tmp_path / "audit/qa.json").read_text())
    assert code in {finding["code"] for finding in qa["findings"]}
    if fault == "child":
        assert len(scene.label.submobjects) > len(scene.label._research_glyphs)


def test_derived_number_transform_still_rejected(tmp_path, configured):
    scene = make_scene(tmp_path)
    number = scene.derived_number("number", source="value", domain=(0, 6), position=(0, 2, 0))
    target = Text("9.99", font=FONT, font_size=30)
    assert "text_transform" in {f["code"] for f in scene.check_animations([Transform(number, target)])}


def test_ordinary_scene_retains_audited_renderer_factory(tmp_path, configured):
    scene = make_scene(tmp_path)
    ordinary = ResearchScene(spec=scene.spec, timeline=scene.timeline, slide_id="s", theme=scene.theme,
        audit_dir=tmp_path / "ordinary", output_folder=tmp_path / "ordinary-slides")
    assert type(ordinary.renderer) is _AuditedRenderer

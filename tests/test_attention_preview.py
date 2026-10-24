"""Independent oracle for the authored 55-second Attention experiment."""
import importlib.util
import math
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1] / "assets/attention-preview"


@pytest.fixture(scope="module")
def model():
    path = ROOT / "src/model.py"
    if not path.is_file():
        def missing(*args):
            pytest.fail("original attention model is missing")
        return missing
    spec = importlib.util.spec_from_file_location("attention_test_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.attention_state


def oracle(t):
    # Polynomial expanded independently, not the model's interpolation helper.
    if t < 10:
        q, v2 = 0.0, 6.0
    elif t < 25:
        u = (t - 10) / 15
        q, v2 = math.log(3) * (3*u*u - 2*u*u*u), 6.0
    elif t < 38:
        u = (t - 25) / 13
        q, v2 = math.log(3) * (1 - 6*u*u + 4*u*u*u), 6.0
    elif t < 42:
        u = (t - 38) / 4
        q, v2 = math.log(3) * (-1 + 6*u*u - 4*u*u*u), 6.0
    elif t < 50:
        u = (t - 42) / 8
        q, v2 = math.log(3), 6 + 12*u*u - 8*u*u*u
    else:
        q, v2 = math.log(3), 10.0
    a2 = 1 / (1 + math.exp(-q))
    return dict(q=q, k1=0.0, k2=1.0, v1=2.0, v2=v2, s1=0.0,
                s2=q, e1=1.0, e2=math.exp(q), a1=1-a2, a2=a2,
                y=2*(1-a2) + v2*a2)


def test_all_825_states_match_independent_six_stage_oracle(model):
    for frame in range(825):
        actual = model(frame, 15)
        assert actual == pytest.approx(oracle(frame/15), abs=1e-10)
        assert all(math.isfinite(value) for value in actual.values())
        assert math.copysign(1, actual["s1"]) == 1  # The fixed zero score must not display -0.00.
        assert actual["a1"] >= 0 and actual["a2"] >= 0
        assert actual["a1"] + actual["a2"] == pytest.approx(1, abs=1e-9)
        assert actual["y"] == pytest.approx(actual["a1"]*actual["v1"] + actual["a2"]*actual["v2"], abs=1e-8)
        assert actual["v1"] <= actual["y"] <= actual["v2"]


@pytest.mark.parametrize("second,weights,y", [(0, [.5,.5],4), (25,[.25,.75],5),
    (38,[.75,.25],3), (42,[.25,.75],5), (50,[.25,.75],8)])
def test_exact_stage_endpoints(model, second, weights, y):
    state = model(second*15, 15)
    assert [state["a1"],state["a2"]] == pytest.approx(weights, abs=1e-9)
    assert state["y"] == pytest.approx(y, abs=1e-8)


def test_value_stage_preserves_query_keys_and_weights(model):
    anchor = model(630,15)
    for frame in range(630,751):
        state = model(frame,15)
        for key in ("q","k1","k2","v1","s1","s2","e1","e2","a1","a2"):
            assert state[key] == anchor[key]
    assert model(749,15)["v2"] < model(750,15)["v2"]


def test_profiles_agree_at_every_common_time(model):
    for frame in range(825):
        assert model(frame,15) == model(frame*4,60)


@pytest.mark.parametrize("frame,fps", [(-1,15),(825,15),(3300,60),(True,15),
    (1.0,15),(0,True),(0,0),(0,-1),(0,15.0),(0,float("nan")),(None,15)])
def test_invalid_time_inputs_fail_explicitly(model, frame, fps):
    with pytest.raises(ValueError):
        model(frame,fps)


@pytest.mark.parametrize("theme_name", ["midnight", "paper", "slate", "custom"])
def test_authored_scene_all_frames_geometry_and_derived_labels(tmp_path, monkeypatch, theme_name):
    # Catches independently animated geometry, moving numeric lanes, wrong
    # exponential scale, normalized lengths, point mapping or phase order.
    scene_path = ROOT / "src/scenes.py"
    assert scene_path.is_file(), "original Attention scene is missing"
    import json
    import yaml
    from manim import tempconfig
    from research.layout import check_frame
    from research.preview_timeline import build_preview_timeline
    from research.scene import ensure_font
    from research.themes import load_theme

    monkeypatch.syspath_prepend(str(scene_path.parent))
    # Isolate the template's plain sibling import from unrelated suite modules.
    model_spec = importlib.util.spec_from_file_location("model", ROOT / "src/model.py")
    local_model = importlib.util.module_from_spec(model_spec)
    model_spec.loader.exec_module(local_model)
    monkeypatch.setitem(sys.modules, "model", local_model)
    module_spec = importlib.util.spec_from_file_location("attention_test_scene", scene_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    spec = yaml.safe_load((ROOT / "planning/preview.yaml").read_text())
    authored = json.loads((ROOT / "planning/timing-draft.json").read_text())
    timeline = build_preview_timeline(spec, authored, 15)
    ensure_font()
    checked = []
    with tempconfig({"disable_caching": True, "frame_rate": 15,
                     "write_to_movie": False, "save_last_frame": False,
                     "pixel_width": 960, "pixel_height": 540,
                     "media_dir": str(tmp_path / "media"), "verbosity": "ERROR"}):
        theme = load_theme(theme_name, {"colors": {"primary": "#ABCDEF",
            "secondary": "#789ABC", "accent": "#FEDCBA"}} if theme_name == "custom" else None)
        scene = module.AttentionPreview(spec=spec, timeline=timeline,
            slide_id="attention", theme=theme,
            audit_dir=tmp_path / "qa", output_folder=tmp_path / "slides")

        def inspect_beat(beat_id):
            beat = timeline["slides"][0]["beats"][len(checked)]
            assert beat_id == beat["id"]
            scene._preview_steps = beat["frames"]
            for field, role in (("s1","primary"),("s2","secondary"),
                                ("v1","primary"),("v2","secondary"),("y","accent")):
                assert scene.dots[field].get_color().to_hex() == theme["colors"][role]
            frames = (range(beat["start_frame"], beat["end_frame"]) if theme_name == "midnight"
                      else [beat["start_frame"], beat["end_frame"]-1])
            for frame in frames:
                scene._frame_count = frame
                scene._prepare_preview_frame()
                expected = oracle(frame / 15)
                records = scene.observed_objects()
                assert check_frame(records, frame, scene.layout, contacts=scene._math_contacts) == []
                assert scene._copy_findings(records) == []
                objects = {r["id"]: r for r in records}
                for field in ("q","s1","s2","e1","e2","a1","a2","v1","v2","y"):
                    number = objects[f"number_{field}"]["derived_number"]
                    assert number["unrounded"] == pytest.approx(expected[field], abs=1e-10)
                    assert abs(float(number["display"])-expected[field]) <= .005 + 1e-12
                for field in ("e1", "e2"):
                    box = objects[f"bar_{field}"]["geometry"]["bounds"]
                    assert box[2]-box[0] == pytest.approx(.9 * expected[field])
                    assert box[0] == pytest.approx(-2.1)
                for field in ("a1", "a2"):
                    box = objects[f"bar_{field}"]["geometry"]["bounds"]
                    assert box[2]-box[0] == pytest.approx(3.2 * expected[field])
                for field in ("v1","v2","y"):
                    assert objects[f"dot_{field}"]["geometry"]["center"] == pytest.approx(
                        [2.6+(expected[field]-2)*3.5/8, -1.3])
                for field, y in (("s1",.5),("s2",-1.15)):
                    assert objects[f"dot_{field}"]["geometry"]["center"] == pytest.approx(
                        [-4.85 + expected[field]*.7, y])
            checked.append(beat_id)
        monkeypatch.setattr(scene, "preview_beat", inspect_beat)
        scene.construct()
    assert len(checked) == 6


def test_author_timings_and_readme_registry_are_synchronized():
    import json
    import yaml
    from research.preview_timeline import build_preview_timeline
    spec = yaml.safe_load((ROOT / "planning/preview.yaml").read_text())
    assert spec["audience_text"]["readme"] == (ROOT/"README.md").read_text()
    assert spec["audience_text"]["source_readme"] == (ROOT/"source/README.md").read_text()
    for profile, fps, frames in (("draft",15,825),("final",60,3300)):
        authored = json.loads((ROOT/f"planning/timing-{profile}.json").read_text())
        timeline = build_preview_timeline(spec,authored,fps)
        assert timeline["total_frames"] == frames
        assert [beat["frames"]/fps for beat in timeline["slides"][0]["beats"]] == [10,15,13,4,8,5]

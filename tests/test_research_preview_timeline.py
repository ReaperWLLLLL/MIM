"""Voice-free preview contracts and exact authored integer frame intervals."""
import copy
import importlib

import pytest

from research.spec import audience_copy, content_hash, validate_text_review


def api():
    try:
        return importlib.import_module("research.preview_timeline")
    except ModuleNotFoundError:
        pytest.fail("research.preview_timeline public interfaces are missing")


@pytest.fixture
def inputs(tmp_path):
    (tmp_path / "scene.py").write_text("# source\n", encoding="utf-8")
    spec = {"schema_version": "research-preview-spec-1",
            "project": {"title": "注意力", "theme": "midnight", "source_files": ["scene.py"]},
            "slides": [{"id": "s1", "scene_class": "Attention",
                        "screen_text": {"query": "查询"},
                        "beats": [{"id": f"b{i}", "screen_text": ["query"]} for i in range(6)]}]}
    authored = {"schema_version": "research-authored-timeline-1", "mode": "silent-preview", "fps": 15,
                "slides": [{"id": "s1", "beats": [{"id": f"b{i}", "frames": frames}
                           for i, frames in enumerate([150, 225, 195, 60, 120, 75])]}]}
    return spec, authored, tmp_path


def test_voice_free_preview_contract(inputs):
    spec, _, root = inputs
    before = copy.deepcopy(spec)
    assert api().validate_preview_spec(spec, root) == []
    assert spec == before
    assert "voice" not in spec
    assert validate_text_review(spec)  # Validation never fabricates manual approval.


def test_exact_authored_intervals(inputs):
    spec, authored, _ = inputs
    before = copy.deepcopy((spec, authored))
    timeline = api().build_preview_timeline(spec, authored, 15)
    assert timeline["schema_version"] == "research-preview-timeline-1"
    assert timeline["mode"] == "silent-preview"
    assert timeline["total_frames"] == 825
    beats = timeline["slides"][0]["beats"]
    assert [b["start_frame"] for b in beats] == [0, 150, 375, 570, 630, 750]
    assert [b["end_frame"] for b in beats] == [150, 375, 570, 630, 750, 825]
    assert [b["local_end_frame"] for b in beats] == [150, 375, 570, 630, 750, 825]
    assert timeline["duration_seconds"] == 55
    assert timeline["spec_hash"] == content_hash(spec)
    assert timeline["authored_hash"] == content_hash(authored)
    assert api().validate_preview_timeline(timeline, spec, authored, 15) == []
    assert (spec, authored) == before


def test_slide_local_intervals_reset_without_global_gaps(inputs):
    spec, authored, _ = inputs
    slide = copy.deepcopy(spec["slides"][0]); slide.update(id="s2", scene_class="Second")
    spec["slides"].append(slide)
    slide = copy.deepcopy(authored["slides"][0]); slide["id"] = "s2"
    authored["slides"].append(slide)
    timeline = api().build_preview_timeline(spec, authored, 15)
    second = timeline["slides"][1]
    assert (second["start_frame"], second["end_frame"], second["frames"]) == (825, 1650, 825)
    assert (second["beats"][0]["start_frame"], second["beats"][0]["local_start_frame"]) == (825, 0)


def test_distinct_slides_can_share_one_valid_scene_class(inputs):
    spec, authored, root = inputs
    second = copy.deepcopy(spec["slides"][0])
    second["id"] = "s2"
    spec["slides"].append(second)
    authored_second = copy.deepcopy(authored["slides"][0])
    authored_second["id"] = "s2"
    authored["slides"].append(authored_second)
    assert api().validate_preview_spec(spec, root) == []
    timeline = api().build_preview_timeline(spec, authored, 15)
    assert [slide["id"] for slide in timeline["slides"]] == ["s1", "s2"]
    assert timeline["total_frames"] == 1650
    assert api().validate_preview_timeline(timeline, spec, authored, 15) == []


@pytest.mark.parametrize("value", [True, False, 1.0, 0, -1, float("inf"), float("nan"), None, "150"])
@pytest.mark.parametrize("field", ["frames", "fps", "profile_fps"])
def test_nonpositive_or_noninteger_frames_and_rates_fail(inputs, value, field):
    spec, authored, _ = inputs
    fps = 15
    if field == "frames":
        authored["slides"][0]["beats"][0]["frames"] = value
    elif field == "fps":
        authored["fps"] = value
    else:
        fps = value
    with pytest.raises(ValueError):
        api().build_preview_timeline(spec, authored, fps)
    assert api().validate_preview_timeline({}, spec, authored, fps)


def test_authored_fps_must_match_profile_without_scaling(inputs):
    spec, authored, _ = inputs
    with pytest.raises(ValueError, match="fps"):
        api().build_preview_timeline(spec, authored, 60)


@pytest.mark.parametrize("target", ["spec", "authored"])
@pytest.mark.parametrize("change", ["duplicate_slide", "duplicate_beat", "missing", "extra", "reordered", "empty"])
def test_invalid_ids_and_inventory_fail_closed(inputs, target, change):
    spec, authored, _ = inputs
    data = spec if target == "spec" else authored
    beats = data["slides"][0]["beats"]
    if change == "duplicate_slide":
        data["slides"].append(copy.deepcopy(data["slides"][0]))
    elif change == "duplicate_beat":
        beats[1]["id"] = beats[0]["id"]
    elif change == "missing":
        beats.pop()
    elif change == "extra":
        extra = copy.deepcopy(beats[0]); extra["id"] = "extra"; beats.append(extra)
    elif change == "reordered":
        beats.reverse()
    else:
        data["slides"] = []
    with pytest.raises(ValueError):
        api().build_preview_timeline(spec, authored, 15)


@pytest.mark.parametrize("location", ["root", "project", "slide", "beat"])
@pytest.mark.parametrize("field", ["voice", "audio", "narration", "unknown"])
def test_spec_rejects_audio_and_unknown_fields(inputs, location, field):
    spec, authored, root = inputs
    obj = {"root": spec, "project": spec["project"], "slide": spec["slides"][0],
           "beat": spec["slides"][0]["beats"][0]}[location]
    obj[field] = "forbidden"
    assert api().validate_preview_spec(spec, root)
    with pytest.raises(ValueError):
        api().build_preview_timeline(spec, authored, 15)


@pytest.mark.parametrize("location", ["root", "slide", "beat"])
def test_authored_rejects_audio_fields(inputs, location):
    spec, authored, _ = inputs
    obj = {"root": authored, "slide": authored["slides"][0], "beat": authored["slides"][0]["beats"][0]}[location]
    obj["audio"] = {}
    with pytest.raises(ValueError):
        api().build_preview_timeline(spec, authored, 15)


@pytest.mark.parametrize("value", ["../scene.py", "/tmp/scene.py", "C:\\scene.py", "a/../scene.py", "missing.py", ".", ""])
def test_source_paths_must_exist_inside_project(inputs, value):
    spec, _, root = inputs
    spec["project"]["source_files"] = [value]
    assert api().validate_preview_spec(spec, root)


def test_escaping_symlink_is_not_a_source_or_theme(inputs, tmp_path):
    spec, _, root = inputs
    outside = tmp_path.parent / (tmp_path.name + "-outside.yaml")
    outside.write_text("font_family: Microsoft YaHei\n", encoding="utf-8")
    (root / "escape.yaml").symlink_to(outside)
    spec["project"]["source_files"] = ["escape.yaml"]
    assert api().validate_preview_spec(spec, root)
    spec["project"].update(source_files=["scene.py"], theme="custom", theme_custom="escape.yaml")
    assert api().validate_preview_spec(spec, root)


@pytest.mark.parametrize("field,value", [("theme", "unknown"), ("theme", []), ("title", " "), ("source_files", []), ("source_files", [False])])
def test_invalid_project_fields_return_findings(inputs, field, value):
    spec, _, root = inputs
    spec["project"][field] = value
    assert api().validate_preview_spec(spec, root)


@pytest.mark.parametrize("change", ["empty", "invalid_key", "empty_text", "unknown_ref", "bad_refs", "bad_id", "bad_class", "keyword_class"])
def test_screen_text_and_identifiers_are_validated(inputs, change):
    spec, _, root = inputs
    slide = spec["slides"][0]
    if change == "empty": slide["screen_text"] = {}
    elif change == "invalid_key": slide["screen_text"] = {"bad key": "查询"}
    elif change == "empty_text": slide["screen_text"]["query"] = " "
    elif change == "unknown_ref": slide["beats"][0]["screen_text"] = ["missing"]
    elif change == "bad_refs": slide["beats"][0]["screen_text"] = [False]
    elif change == "bad_id": slide["beats"][0]["id"] = "bad id"
    elif change == "bad_class": slide["scene_class"] = "123Scene"
    else: slide["scene_class"] = "class"
    assert api().validate_preview_spec(spec, root)


def test_visual_only_beat_and_reviewed_audience_copy(inputs):
    spec, _, root = inputs
    spec["slides"][0]["beats"][0]["screen_text"] = []
    spec["audience_text"] = {"report": ["权重之和为一。"]}
    digest = content_hash(audience_copy(spec))
    spec["text_review"] = {"content_hash": digest, **{name: {"status": "approved", "content_hash": digest}
                            for name in ("humanizer", "humanizer-zh")}}
    assert api().validate_preview_spec(spec, root) == []
    assert validate_text_review(spec) == []
    spec["audience_text"]["report"] = ["本页将展示机制"]
    assert api().validate_preview_spec(spec, root)
    assert validate_text_review(spec)


def test_custom_theme_uses_existing_loader(inputs):
    spec, _, root = inputs
    spec["project"].update(theme="custom", theme_custom="theme.yaml")
    (root / "theme.yaml").write_text("font_family: Microsoft YaHei\n", encoding="utf-8")
    assert api().validate_preview_spec(spec, root) == []
    (root / "theme.yaml").write_text("font_sizes: {title: 1, body: 1, caption: 1}\n", encoding="utf-8")
    assert api().validate_preview_spec(spec, root)


@pytest.mark.parametrize("value", [None, [], True, "invalid", 1, {"slides": [None]}])
def test_malformed_validation_inputs_return_findings(inputs, value):
    spec, authored, root = inputs
    assert api().validate_preview_spec(value, root)
    assert api().validate_preview_timeline(value, spec, authored, 15)
    assert api().validate_preview_timeline({}, value, authored, 15)
    assert api().validate_preview_timeline({}, spec, value, 15)


@pytest.mark.parametrize("change", ["spec", "authored", "spec_hash", "authored_hash", "timeline_hash", "interval", "local_interval", "extra", "bool_frame"])
def test_tampered_timeline_or_inputs_are_rejected_even_with_rehashed_timeline(inputs, change):
    spec, authored, _ = inputs
    timeline = api().build_preview_timeline(spec, authored, 15)
    if change == "spec": spec["project"]["title"] = "改变"
    elif change == "authored": authored["slides"][0]["beats"][0]["frames"] = 151
    elif change in {"spec_hash", "authored_hash", "timeline_hash"}: timeline[change] = "0" * 64
    elif change == "interval": timeline["slides"][0]["beats"][0]["end_frame"] = 149
    elif change == "local_interval": timeline["slides"][0]["beats"][1]["local_start_frame"] = 0
    elif change == "bool_frame": timeline["slides"][0]["beats"][0]["start_frame"] = False
    else: timeline["audio"] = {}
    if change != "timeline_hash":
        timeline["timeline_hash"] = content_hash({k: v for k, v in timeline.items() if k != "timeline_hash"})
    assert api().validate_preview_timeline(timeline, spec, authored, 15)

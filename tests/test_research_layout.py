"""Real semantic geometry fixtures; no renderer mocks or source-text assertions."""
import copy
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def check(objects, frame=0, config=None):
    try:
        module = importlib.import_module("research.layout")
    except ModuleNotFoundError:
        pytest.fail("research.layout.check_frame is not implemented")
    return module.check_frame(objects, frame, {} if config is None else config)


def obj(identifier, bbox, kind="shape", **extra):
    record = {"id": identifier, "kind": kind, "bbox": bbox, "visible": True,
              "registered": True, "parent": None, "role": None, "effective_font_size": None}
    if kind in {"text", "formula", "subtitle"}:
        record.update(role="body", effective_font_size=30)
    record.update(extra)
    return record


def codes(findings):
    return {f["code"] for f in findings}


def test_separated_semantic_objects_are_valid_and_inputs_are_unchanged():
    objects = [obj("a", [-3, 0, -2, 1], "text"), obj("b", [2, 0, 3, 1])]
    before = copy.deepcopy(objects)
    assert check(objects, frame=19) == []
    assert objects == before


def test_finite_viewport_endpoints_cannot_overflow_derived_geometry():
    findings = check([], config={"viewport": [-1e308, -1e308, 1e308, 1e308]})
    assert any(f["code"] == "invalid_config" and "viewport" in f["message"] for f in findings)
    assert check([]) == []


@pytest.mark.parametrize("paint", [
    {"path_bbox": None, "inner_bbox": [-.5, -.5, .5, .5]},
    {"path_bbox": False, "inner_bbox": [-.5, -.5, .5, .5]},
    {"paint_radius": "wide"},
    {"inner_bbox": [-.5, -.5, .5, .5]},
    {"path_bbox": [-.8, -.8, .8, .8], "paint_radius": .2, "inner_bbox": [-.8, -.8, .8, .8]},
])
def test_malformed_paint_evidence_returns_findings_without_expanding_inner_area(paint):
    assert "invalid_object" in codes(check([obj("box", [-1, -1, 1, 1], "container", **paint)]))


def test_observed_container_inner_area_is_inset_by_paint():
    assert check([obj("box", [-1, -1, 1, 1], "container", path_bbox=[-.8, -.8, .8, .8],
                      paint_radius=.2, inner_bbox=[-.6, -.6, .6, .6])]) == []


def test_static_text_collision_reports_pair_frame_and_fix():
    findings = check([obj("a", [-1, 0, 1, 1], "text"), obj("b", [0, 0, 2, 1], "text")], 42)
    collision = next(f for f in findings if f["code"] == "collision")
    assert collision["object_ids"] == ["a", "b"]
    assert collision["frame"] == 42
    assert collision["severity"] == "error" and collision["message"] and collision["suggestion"]


def test_motion_middle_collision_is_not_exempted():
    moving = obj("moving", [-3, 0, -2, 1], moving=True)
    stationary = obj("fixed", [0, 0, 1, 1])
    assert check([moving, stationary], 0) == []
    moving["bbox"] = [0, 0, 1, 1]
    assert "collision" in codes(check([moving, stationary], 30))
    moving["bbox"] = [3, 0, 4, 1]
    assert check([moving, stationary], 60) == []


def test_undesignated_containment_does_not_hide_collision():
    assert "collision" in codes(check([obj("card", [-2, -2, 2, 2], "container"),
                                           obj("text", [-1, 0, 1, 1], "text")]))


def test_explicit_container_child_with_padding_passes():
    assert check([obj("card", [-2, -2, 2, 2], "container"),
                  obj("text", [-1, 0, 1, 1], "text", parent="card")]) == []


@pytest.mark.parametrize("bbox", [[-1.95, 0, 1, 1], [-3, 0, 1, 1]])
def test_parent_child_border_touch_and_overflow_are_rejected(bbox):
    result = check([obj("card", [-2, -2, 2, 2], "container"),
                    obj("text", bbox, "text", parent="card")], 11)
    assert "container_overflow" in codes(result)
    assert any(f["object_ids"] == ["text", "card"] and f["frame"] == 11 for f in result)


def test_parent_reference_cannot_authorize_noncontainer_or_cycles():
    assert "invalid_parent" in codes(check([obj("a", [-2, -2, 2, 2]),
                                               obj("b", [-1, 0, 1, 1], parent="a")]))
    assert "invalid_parent" in codes(check([obj("a", [-2, -2, 2, 2], "container", parent="b"),
                                               obj("b", [-1, 0, 1, 1], "container", parent="a")]))


@pytest.mark.parametrize("role,size", [("body", 29), ("title", 47), ("caption", 19), ("tiny", 12)])
def test_effective_font_size_catches_scaling_and_unknown_roles(role, size):
    assert "font_size" in codes(check([obj("copy", [0, 0, 1, 1], "text", role=role, effective_font_size=size)]))


def test_custom_fixed_font_group_is_honored_not_arbitrary_shrinking():
    custom = {"font_sizes": {"title": 50, "body": 32, "caption": 22}}
    assert check([obj("copy", [0, 0, 1, 1], "text", effective_font_size=32)], config=custom) == []
    assert "font_size" in codes(check([obj("copy", [0, 0, 1, 1], "text", effective_font_size=31)], config=custom))


def test_unregistered_visible_foreground_is_not_silently_ignored():
    result = check([obj("raw", [0, 0, 1, 1], registered=False)], 8)
    assert "unregistered" in codes(result)
    assert any(f["object_ids"] == ["raw"] and f["frame"] == 8 for f in result)


def test_background_exclusion_requires_full_viewport_and_no_parent():
    assert check([obj("bg", [-64/9, -4, 64/9, 4], "background"),
                  obj("a", [0, 0, 1, 1])]) == []
    assert "invalid_background" in codes(check([obj("fake", [0, 0, 1, 1], "background")]))


def test_visibility_uses_opacity_and_half_open_display_interval():
    record = obj("hidden", [0, 0, 1, 1], registered=False, opacity=0)
    assert check([record]) == []
    record.update(opacity=1, start_frame=3, end_frame=6)
    assert check([record], 2) == []
    assert "unregistered" in codes(check([record], 3))
    assert check([record], 6) == []


def test_default_safety_margin_and_overridden_viewport_are_checked():
    assert "safe_boundary" in codes(check([obj("edge", [-7, 0, -6, 1])]))
    assert check([obj("inside", [-6.3, -3.5, -5, -3])]) == []
    assert "safe_boundary" in codes(check([obj("edge", [4.4, 0, 4.9, 1])], config={"viewport": [-5, -4, 5, 4]}))


def test_independent_objects_need_gap_even_without_intersection():
    assert "collision" in codes(check([obj("a", [-1, 0, 0, 1]), obj("b", [0.05, 0, 1, 1])]))


def test_subtitle_zone_reserves_region_and_constrains_subtitles():
    cfg = {"subtitle_zone": [-6, -3.5, 6, -2.8]}
    assert "subtitle_zone" in codes(check([obj("chart", [0, -3.3, 1, -2.5])], config=cfg))
    assert check([obj("subtitle", [-2, -3.4, 2, -3], "subtitle", role="caption", effective_font_size=20)], config=cfg) == []
    assert "subtitle_zone" in codes(check([obj("subtitle", [-2, -2, 2, -1], "subtitle")], config=cfg))


def nodes_and_connector():
    return [obj("left", [-3, 0, -2, 1]), obj("right", [2, 0, 3, 1]),
            obj("link", [-2, .5, 2, .5], "connector", endpoints=[
                {"object_id": "left", "point": [-2, .5]},
                {"object_id": "right", "point": [2, .5]}])]


def test_connector_only_contacts_its_explicit_valid_node_endpoints():
    assert check(nodes_and_connector()) == []


def test_connector_does_not_get_global_collision_exemption():
    objects = nodes_and_connector() + [obj("label", [-.5, .2, .5, .8], "text")]
    assert any(f["code"] == "collision" and f["object_ids"] == ["link", "label"] for f in check(objects))


def test_connector_bbox_cannot_expand_endpoint_exemption_into_node_interiors():
    objects = nodes_and_connector()
    objects[2]["bbox"] = [-2.5, .3, 2.5, .7]
    assert "invalid_connector" in codes(check(objects))


def test_observed_triangular_arrow_tip_is_included_in_actual_bbox():
    objects = nodes_and_connector()
    objects[2].update(bbox=[-2, .35, 2, .65], tips=[
        {"endpoint": 1, "vertices": [[2, .5], [1.7, .35], [1.7, .65]]}])
    assert check(objects) == []


def test_double_arrow_tips_and_bounded_stroke_have_truthful_painted_bbox():
    objects = nodes_and_connector()
    objects[2].update(bbox=[-2.02, .33, 2.02, .67], stroke_radius=.02, tips=[
        {"endpoint": 0, "vertices": [[-2, .5], [-1.7, .35], [-1.7, .65]]},
        {"endpoint": 1, "vertices": [[2, .5], [1.7, .35], [1.7, .65]]}])
    assert check(objects) == []


def test_actual_arrow_tip_bbox_still_collides_with_unrelated_text():
    objects = nodes_and_connector()
    objects[2].update(bbox=[-2, .35, 2, .65], tips=[
        {"endpoint": 1, "vertices": [[2, .5], [1.7, .35], [1.7, .65]]}])
    objects.append(obj("copy", [1.6, .6, 1.9, 1], "text"))
    findings = check(objects)
    assert "invalid_connector" not in codes(findings)
    assert any(f["code"] == "collision" and f["object_ids"] == ["link", "copy"] for f in findings)


def test_wide_short_arrow_tip_must_not_penetrate_its_endpoint_node():
    objects = [obj("left", [-3, 0, -2, 1]), obj("right", [2, -2.5, 3, -1.5]),
               obj("link", [-2.112, -2, 2, 1.154], "connector", endpoints=[
                   {"object_id": "left", "point": [-2, 1]},
                   {"object_id": "right", "point": [2, -2]}], tips=[
                       {"endpoint": 0, "vertices": [[-2, 1], [-1.872, 1.154], [-2.112, .834]]}])]
    assert "invalid_connector" in codes(check(objects))


@pytest.mark.parametrize("extra", [
    {"tips": "invalid"},
    {"tips": [{"endpoint": 1, "vertices": [[1.9, .5], [1.7, .35], [1.7, .65]]}]},
    {"tips": [{"endpoint": 1, "vertices": [[2, .5], [2.2, .35], [2.2, .65]]}]},
    {"tips": [{"endpoint": 1, "vertices": [[2, .5], [1.7, -.5], [1.7, 1.5]]}]},
    {"tips": [{"endpoint": 1, "vertices": [[2, .5], [1, .35], [1, .65]]}]},
    {"tips": [{"endpoint": "end", "vertices": [[2, .5], [1.7, .35], [1.7, .65]]}]},
    {"stroke_radius": .5}, {"stroke_radius": float("nan")},
])
def test_connector_tip_and_stroke_metadata_cannot_expand_narrow_exemption(extra):
    objects = nodes_and_connector()
    objects[2].update(extra)
    assert "invalid_connector" in codes(check(objects))


def test_formula_must_use_the_body_font_role():
    assert "font_size" in codes(check([obj("formula", [0, 0, 1, 1], "formula", role="title", effective_font_size=48)]))


def test_full_backing_is_not_an_unregistered_foreground():
    assert check([obj("bg", [-64/9, -4, 64/9, 4], "background", registered=False)]) == []


def test_nested_explicit_containers_pass_but_sibling_text_still_collides():
    objects = [obj("outer", [-3, -2, 3, 2], "container"),
               obj("inner", [-2, -1, 2, 1.5], "container", parent="outer"),
               obj("copy", [-1, 0, 1, 1], "text", parent="inner")]
    assert check(objects) == []
    objects.append(obj("second", [0, 0, 1, 1], "text", parent="inner"))
    assert any(f["code"] == "collision" and f["object_ids"] == ["copy", "second"] for f in check(objects))


@pytest.mark.parametrize("change", ["missing", "inside", "wrong_bbox", "crossing_node"])
def test_invalid_connector_relations_cannot_suppress_collisions(change):
    objects = nodes_and_connector()
    link = objects[2]
    if change == "missing":
        link["endpoints"][0]["object_id"] = "absent"
    elif change == "inside":
        link["endpoints"][0]["point"] = [-2.5, .5]
        link["bbox"][0] = -2.5
    elif change == "wrong_bbox":
        link["bbox"] = [-1, .5, 1, .5]
    else:
        link["endpoints"][0]["point"] = [-3, .5]
        link["bbox"][0] = -3
    assert "invalid_connector" in codes(check(objects))


@pytest.mark.parametrize("objects,frame,config", [
    (None, 0, {}), ([None], 0, {}), ([{}], 0, {}),
    ([obj("bad", [0, 0, float("nan"), 1])], 0, {}),
    ([obj("bad", [1, 0, 0, 1])], 0, {}),
    ([obj("same", [0, 0, 1, 1]), obj("same", [2, 0, 3, 1])], 0, {}),
    ([obj("bad", [0, 0, 1, 1], visible="yes")], 0, {}),
    ([obj("bad", [0, 0, 1, 1], opacity=float("nan"))], 0, {}),
    ([], -1, {}), ([], True, {}), ([], 0, []),
    ([], 0, {"margin": 0}), ([], 0, {"font_sizes": {"body": 12}}),
    ([], 0, {"viewport": [0, 0, 0, 1]}),
    ([obj("bad", [0, 0, 1, 1], start_frame="bad", end_frame=5)], 0, {}),
    ([obj("bad", [0, 0, 10**999, 1])], 0, {}),
    ([], 0, {"min_gap": 0}), ([], 0, {"container_padding": 0}),
    ([], 0, {"font_tolerance": 5}), ([], 0, {"opacity_threshold": .99}),
])
def test_malformed_inputs_return_actionable_findings_not_crashes(objects, frame, config):
    findings = check(objects, frame, config)
    assert findings
    assert all(f["severity"] == "error" and f["message"] and f["suggestion"] for f in findings)

"""Narrow mathematical contacts, including real Manim observer boundary tests."""
import copy
import importlib
import io
import json

import numpy as np
import pytest

from research.layout import check_frame


def validate(objects, frame, contacts):
    return importlib.import_module("research.math_contacts").validate_contacts(objects, frame, contacts)


def shape(identifier, geometry, paint=.01, **extra):
    if geometry["type"] == "line":
        p, q = geometry["endpoints"]
        box = [min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1])]
    elif geometry["type"] == "circle":
        x, y = geometry["center"]
        r = geometry["radius"]
        box = [x-r, y-r, x+r, y+r]
    else:
        box = geometry["bounds"]
    return {"id": identifier, "kind": "shape", "geometry": geometry,
            "path_bbox": box, "paint_radius": paint,
            "bbox": [box[0]-paint, box[1]-paint, box[2]+paint, box[3]+paint],
            "visible": True, "registered": True, "parent": None,
            "role": None, "effective_font_size": None, **extra}


def point_axis(center=(0, 0), radius=.08, paint=.01):
    return [shape("axis", {"type": "line", "endpoints": [[-2, 0], [2, 0]]}, paint),
            shape("output", {"type": "circle", "center": list(center), "radius": radius}, paint)]


def adjacent():
    return [shape("left", {"type": "rectangle", "bounds": [-2, -1, 0, 1]}),
            shape("right", {"type": "rectangle", "bounds": [0, -1, 2, 1]})]


def contact(kind="point_on_number_line", objects=("axis", "output"), **extra):
    return {"id": "relation", "kind": kind, "objects": list(objects),
            "start_frame": 0, "end_frame": 10, **extra}


@pytest.mark.parametrize("objects,relation,pair", [
    (point_axis(), contact(), ("axis", "output")),
    (adjacent(), contact("adjacent_weight_segments", ("left", "right")), ("left", "right")),
])
def test_valid_declared_contacts_pass_without_mutation(objects, relation, pair):
    before = copy.deepcopy((objects, relation))
    assert validate(objects, 0, [relation]) == ([], {pair})
    assert check_frame(objects, 0, {}, contacts=[relation]) == []
    assert (objects, relation) == before
    assert any(f["code"] == "collision" for f in check_frame(objects, 0, {}, contacts=()))


@pytest.mark.parametrize("frame,relation", [
    (0, contact(objects=("axis", "missing"))),
    (0, contact(objects=("axis", "axis"))),
    (0, contact(kind="arbitrary_overlap")),
    (0, contact(start_frame=True)),
    (0, contact(end_frame=0)),
    (10, contact()),
    (0, contact(start_frame=1)),
])
def test_invalid_or_inactive_contact_never_hides_original_collision(frame, relation):
    findings, pairs = validate(point_axis(), frame, [relation])
    assert not pairs
    if not (frame == 10 or relation["start_frame"] == 1 and relation["start_frame"] is not True):
        assert findings
    assert any(f["code"] == "collision" for f in check_frame(point_axis(), frame, {}, contacts=[relation]))


@pytest.mark.parametrize("change", [
    {"kind": "text", "role": "body", "effective_font_size": 30},
    {"kind": "background"}, {"kind": "container"}, {"kind": "connector"},
    {"registered": False}, {"visible": False}, {"opacity": 0},
    {"effective_font_size": 30}, {"role": "body"}, {"geometry": None},
])
def test_ineligible_objects_cannot_claim_math_contact(change):
    objects = point_axis()
    objects[1].update(change)
    findings, pairs = validate(objects, 0, [contact()])
    assert findings and not pairs


@pytest.mark.parametrize("relations", [
    [contact(), contact()],
    [contact(), contact(id="other")],
    [contact(), contact(id="other", objects=["output", "axis"])],
])
def test_duplicate_relations_fail_closed_for_both_declarations(relations):
    findings, pairs = validate(point_axis(), 0, relations)
    assert findings and not pairs
    assert any(f["code"] == "collision" for f in check_frame(point_axis(), 0, {}, contacts=relations))


@pytest.mark.parametrize("center,radius,paint", [
    ((2.0001, 0), .08, .01), ((0, .0001), .08, .01),
    ((0, 0), .1001, .01), ((0, 0), .08, .0501),
])
def test_point_endpoint_axis_radius_and_paint_caps_are_numeric(center, radius, paint):
    findings, pairs = validate(point_axis(center, radius, paint), 0, [contact()])
    assert findings and not pairs


def test_geometry_tolerance_is_not_visual_min_gap():
    assert validate(point_axis((0, 5e-9)), 0, [contact()])[1] == {("axis", "output")}
    assert not validate(point_axis((0, 2e-8)), 0, [contact()])[1]
    assert validate(point_axis((2, 0)), 0, [contact()])[0] == []


@pytest.mark.parametrize("bounds", [[-.001, -1, 2, 1], [.001, -1, 2, 1], [0, -.9, 2, 1]])
def test_segments_require_full_shared_vertical_edge_without_interior_overlap(bounds):
    objects = adjacent()
    objects[1] = shape("right", {"type": "rectangle", "bounds": bounds})
    findings, pairs = validate(objects, 0, [contact("adjacent_weight_segments", ("left", "right"))])
    assert findings and not pairs


@pytest.mark.parametrize("factory,relation", [
    (point_axis, contact()), (adjacent, contact("adjacent_weight_segments", ("left", "right"))),
])
def test_claimed_bbox_or_broad_paint_cannot_expand_contact_band(factory, relation):
    objects = factory()
    objects[1]["bbox"][0] -= .2
    assert validate(objects, 0, [relation])[0]
    assert not validate(objects, 0, [relation])[1]
    objects = factory()
    objects[1]["paint_radius"] = .2
    assert not validate(objects, 0, [relation])[1]


def test_valid_contact_does_not_exempt_third_label():
    objects = point_axis()
    label = copy.deepcopy(objects[1])
    label.update(id="label", kind="text", role="body", effective_font_size=30)
    findings = check_frame([*objects, label], 0, {}, contacts=[contact()])
    assert any(f["code"] == "collision" and "label" in f["object_ids"] for f in findings)
    assert not any(f["code"] == "collision" and f["object_ids"] == ["axis", "output"] for f in findings)


@pytest.mark.parametrize("contacts", [None, {}, [None], [contact(objects="axis")]])
def test_malformed_contacts_return_actionable_findings(contacts):
    findings, pairs = validate(point_axis(), 0, contacts)
    assert findings and not pairs
    assert all(f["code"] == "invalid_math_contact" and f["severity"] == "error"
               and f["message"] and f["suggestion"] for f in findings)


def test_scene_observes_real_shapes_and_captures_contact_qa(tmp_path):
    from manim import Circle, Line
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    scene.add(scene.track("axis", Line([-2, 0, 0], [2, 0, 0], stroke_width=1), "shape"),
              scene.track("output", Circle(radius=.08, stroke_width=1, fill_opacity=1), "shape"))
    scene.math_contact("relation", kind="point_on_number_line", objects=("axis", "output"),
                       start_frame=0, end_frame=6)
    records = scene.observed_objects()
    assert validate(records, 0, scene._math_contacts) == ([], {("axis", "output")})
    assert records[0]["geometry"]["endpoints"] == [[-2, 0], [2, 0]]
    assert records[1]["geometry"]["radius"] == pytest.approx(.08)
    scene._trace = io.StringIO()
    scene.capture_frame(np.zeros((360, 640, 3), dtype=np.uint8))
    trace = json.loads(scene._trace.getvalue())
    assert trace["findings"] == [] and trace["math_contacts"] == scene._math_contacts


@pytest.mark.parametrize("variant", ["bent_line", "ellipse", "distorted_circle", "rotated_rectangle", "bowed_rectangle"])
def test_scene_rejects_class_name_only_geometry_evidence(tmp_path, variant):
    from manim import Circle, Line, Rectangle
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    if variant == "bent_line":
        first, second = Line([-2, 0, 0], [2, 0, 0]), Circle(radius=.08)
        first.points[1, 1] += .02
    elif variant in {"ellipse", "distorted_circle"}:
        first, second = Line([-2, 0, 0], [2, 0, 0]), Circle(radius=.08)
        if variant == "ellipse":
            second.stretch(1.2, 0)
        else:
            second.points[1, 0] += .002
    else:
        first, second = Rectangle(width=2, height=2).shift([-1, 0, 0]), Rectangle(width=2, height=2).shift([1, 0, 0])
        if variant == "rotated_rectangle":
            second.rotate(.01)
        else:
            second.points[1, 1] += .02
    ids = ("axis", "output") if "rectangle" not in variant else ("left", "right")
    scene.add(scene.track(ids[0], first, "shape"), scene.track(ids[1], second, "shape"))
    kind = "point_on_number_line" if ids[0] == "axis" else "adjacent_weight_segments"
    findings, pairs = validate(scene.observed_objects(), 0, [contact(kind, ids)])
    assert findings and not pairs


def test_scene_observes_adjacent_rectangles_and_rechecks_after_deformation(tmp_path):
    from manim import Rectangle
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    a = scene.track("left", Rectangle(width=2, height=2, stroke_width=1).shift([-1, 0, 0]), "shape")
    b = scene.track("right", Rectangle(width=2, height=2, stroke_width=1).shift([1, 0, 0]), "shape")
    scene.add(a, b)
    relation = contact("adjacent_weight_segments", ("left", "right"))
    assert validate(scene.observed_objects(), 0, [relation])[0] == []
    b.shift([-.01, 0, 0])
    assert not validate(scene.observed_objects(), 0, [relation])[1]


@pytest.mark.parametrize("fault", ["off_axis", "beyond_endpoint", "large_dot", "wide_stroke"])
def test_observed_point_geometry_and_actual_paint_cannot_bypass_numeric_limits(tmp_path, fault):
    from manim import Circle, Line
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    line = Line([-2, 0, 0], [2, 0, 0], stroke_width=1)
    dot = Circle(radius=.11 if fault == "large_dot" else .08, stroke_width=1, fill_opacity=1)
    if fault == "off_axis":
        dot.shift([0, .001, 0])
    elif fault == "beyond_endpoint":
        dot.shift([2.001, 0, 0])
    elif fault == "wide_stroke":
        line.set_stroke(width=40)
    scene.add(scene.track("axis", line, "shape"), scene.track("output", dot, "shape"))
    records = scene.observed_objects()
    if fault == "wide_stroke":
        assert records[0]["paint_radius"] > .05
    findings, pairs = validate(records, 0, [contact()])
    assert findings and not pairs
    findings = check_frame(records, 0, {}, contacts=[contact()])
    assert {"invalid_math_contact", "collision"} <= {f["code"] for f in findings}


@pytest.mark.parametrize("radius,valid", [(.1, True), (.1001, False)])
def test_translated_max_radius_dot_uses_geometry_tolerance_without_clamping(tmp_path, radius, valid):
    from manim import Circle, Line
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    dot = scene.track("output", Circle(radius=radius, stroke_width=1, fill_opacity=1), "shape")
    scene.add(scene.track("axis", Line([-4, 0, 0], [4, 0, 0], stroke_width=1), "shape"), dot)
    for x in (0, 1, 2, 3):
        dot.move_to([x, 0, 0])
        records = scene.observed_objects()
        observed_radius = next(r["geometry"]["radius"] for r in records if r["id"] == "output")
        findings, pairs = validate(records, 0, [contact()])
        if valid:
            assert findings == [] and pairs == {("axis", "output")}
            assert check_frame(records, 0, {}, contacts=[contact()]) == []
        else:
            assert findings and not pairs
            assert {"invalid_math_contact", "collision"} <= {
                f["code"] for f in check_frame(records, 0, {}, contacts=[contact()])}
    # The x=3 subtraction has floating-point roundoff. Preserve the measured
    # radius rather than clamping geometry or widening the painted envelope.
    if valid:
        assert observed_radius > .1


def test_scene_declaration_duplicates_fail_but_disjoint_pair_intervals_are_legal(tmp_path):
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    scene.math_contact("first", kind="point_on_number_line", objects=("axis", "output"), start_frame=0, end_frame=2)
    with pytest.raises(ValueError, match="duplicate"):
        scene.math_contact("again", kind="point_on_number_line", objects=("output", "axis"), start_frame=1, end_frame=3)
    scene.math_contact("later", kind="point_on_number_line", objects=("output", "axis"), start_frame=2, end_frame=4)
    assert validate(point_axis(), 2, scene._math_contacts) == ([], {("axis", "output")})


@pytest.mark.parametrize("kwargs", [
    {"kind": "overlap"}, {"objects": ("axis", "axis")}, {"objects": ("axis",)},
    {"start_frame": -1}, {"start_frame": True}, {"end_frame": 0},
])
def test_scene_contact_declaration_rejects_bad_contract(tmp_path, kwargs):
    from test_research_scene import make_scene
    scene = make_scene(tmp_path)
    args = {"kind": "point_on_number_line", "objects": ("axis", "output"), "start_frame": 0, "end_frame": 6, **kwargs}
    with pytest.raises(ValueError):
        scene.math_contact("relation", **args)

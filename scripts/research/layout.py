"""Pure per-frame semantic layout checks; call for EVERY final output frame.

Object record (required): id:str, kind:str, bbox:[left,bottom,right,top],
visible:bool, registered:bool, parent:str|None, role:str|None,
effective_font_size:number|None. Text/formula/subtitle require a fixed font role;
any other object carrying a role/font size is checked identically. Optional
opacity defaults 1; start_frame/end_frame use half-open visibility intervals.
The bridge must derive visibility and effective sizes from observed mobjects,
and include unregistered foreground. This function cannot establish coverage.

Container relations require a visible registered kind=container parent and
padding at every link. Only valid explicit ancestor/descendant pairs are exempt
from collision. Siblings and unrelated containers remain checked. A background
is excluded only when it covers the full viewport and has no parent.
Observed path_bbox/paint_radius distinguish path geometry from painted bbox;
container inner_bbox is inset from the path, never enlarged with its border.

Straight connectors require exactly two endpoints [{object_id,point:[x,y]},...].
Each target must be a visible registered non-text, non-connector foreground,
each point must lie on its target path boundary, its paint radius must be <=.05,
and the segment must immediately
leave that target (never cross its interior). Optional tips records contain an
endpoint index 0/1 and three observed triangle vertices; apex equals endpoint,
base is symmetric behind it, tip length <=min(.5,segment_length/2), width<=.5.
Tip polygons cannot overlap either target's interior. Optional stroke_radius
is observed painted padding in scene units, bounded [0,.05] (default 0 for
point-geometry bboxes). Only that bounded paint cap may enter a target edge.
The bbox must equal the segment+observed tips envelope expanded by stroke_radius
(within 1e-8 scene units), never an arbitrary expanded box.
Only a validated connector's own endpoint targets are collision-exempt; all
other pairs use conservative bounding boxes. Curved paths need subdivision
into registered segments, not a fabricated straight endpoint exemption.

Optional contacts grant only a validated pair for its half-open global-frame
interval: a small observed circle centered on an actual segment, or two observed
axis-aligned rectangles sharing a full vertical edge. Geometry/paint envelopes
must match; text, backgrounds, connectors and containers cannot participate.
Invalid contacts produce findings and retain the ordinary collision checks.

Config keys: viewport (default [-64/9,-4,64/9,4]), margin (fraction of EACH
dimension, >=.05 and <.5), min_gap (.1 scene units), container_padding (.15),
font_sizes (48/30/20 complete group), font_tolerance (.01; allowed 0..0.1),
subtitle_zone (None or scene bbox), opacity_threshold (.01; allowed 0..0.01).
min_gap and container_padding must be positive. Unknown keys fail closed.
Subtitle objects are contained in the zone; all other foreground avoids it.
Threshold .01 excludes <=1% opacity as effectively invisible; bridge records
actual opacity, not animation intent. These defaults must be recorded in QA.

Returns error findings {code,severity,frame,object_ids,message,suggestion}.
Malformed input returns actionable findings instead of exceptions. Does not
mutate inputs, interpolate motion, install fonts, or import Manim.
"""
from __future__ import annotations

import math

from .themes import validate_font_sizes
from .math_contacts import validate_contacts


_DEFAULTS = {"viewport": [-64 / 9, -4, 64 / 9, 4], "margin": .05, "min_gap": .1,
             "container_padding": .15, "font_sizes": {"title": 48, "body": 30, "caption": 20},
             "font_tolerance": .01, "subtitle_zone": None, "opacity_threshold": .01}
_TEXT = {"text", "formula", "subtitle"}
_EPS = 1e-8


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _box(value, *, area=False):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(_number(v) for v in value)
            and (value[0] < value[2] and value[1] < value[3] if area
                 else value[0] <= value[2] and value[1] <= value[3]))


def _contains(outer, inner, padding=0):
    return (inner[0] >= outer[0] + padding - _EPS and inner[1] >= outer[1] + padding - _EPS
            and inner[2] <= outer[2] - padding + _EPS and inner[3] <= outer[3] - padding + _EPS)


def _near(a, b, gap):
    return (a[0] < b[2] + gap - _EPS and a[2] > b[0] - gap + _EPS
            and a[1] < b[3] + gap - _EPS and a[3] > b[1] - gap + _EPS)


def _boundary(point, box):
    x, y = point
    return (_contains(box, [x, y, x, y])
            and any(abs(a - b) <= _EPS for a, b in ((x, box[0]), (x, box[2]), (y, box[1]), (y, box[3]))))


def _leaves(point, other, box):
    """A straight segment must head out of a touched boundary, not into node."""
    x, y = point
    dx, dy = other[0] - x, other[1] - y
    return ((abs(x - box[0]) <= _EPS and dx < -_EPS)
            or (abs(x - box[2]) <= _EPS and dx > _EPS)
            or (abs(y - box[1]) <= _EPS and dy < -_EPS)
            or (abs(y - box[3]) <= _EPS and dy > _EPS))


def _polygon_overlaps_box(vertices, box):
    """Convex SAT test: shared boundary alone is not interior overlap."""
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    axes = [(1, 0), (0, 1)]
    for i, vertex in enumerate(vertices):
        other = vertices[(i + 1) % len(vertices)]
        axes.append((other[1] - vertex[1], vertex[0] - other[0]))
    for x, y in axes:
        a = [v[0] * x + v[1] * y for v in vertices]
        b = [v[0] * x + v[1] * y for v in corners]
        if min(max(a), max(b)) - max(min(a), min(b)) <= _EPS:
            return False
    return True


def _connector_envelope(record, endpoints, targets):
    """Validate observed ordinary triangle tips; return exact painted envelope."""
    p0, p1 = (endpoint["point"] for endpoint in endpoints)
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    tips, radius = record.get("tips", []), record.get("stroke_radius", 0)
    if (not _number(length) or length <= _EPS or not isinstance(tips, list) or len(tips) > 2
            or not _number(radius) or not 0 <= radius <= .05):
        return None
    points = [p0, p1]
    seen = set()
    for tip in tips:
        if not isinstance(tip, dict):
            return None
        endpoint, vertices = tip.get("endpoint"), tip.get("vertices")
        if (not isinstance(endpoint, int) or isinstance(endpoint, bool) or endpoint not in (0, 1)
                or endpoint in seen or not isinstance(vertices, (list, tuple)) or len(vertices) != 3
                or any(not isinstance(v, (list, tuple)) or len(v) != 2
                       or not all(_number(c) for c in v) for v in vertices)):
            return None
        seen.add(endpoint)
        apex, other = endpoints[endpoint]["point"], endpoints[1 - endpoint]["point"]
        apex_indices = [i for i, v in enumerate(vertices) if all(abs(v[j] - apex[j]) <= _EPS for j in (0, 1))]
        if len(apex_indices) != 1:
            return None
        base = [v for i, v in enumerate(vertices) if i != apex_indices[0]]
        ux, uy = (other[0] - apex[0]) / length, (other[1] - apex[1]) / length
        projections = [((v[0] - apex[0]) * ux + (v[1] - apex[1]) * uy,
                        -(v[0] - apex[0]) * uy + (v[1] - apex[1]) * ux) for v in base]
        (t0, w0), (t1, w1) = projections
        if (not _EPS < t0 <= min(.5, length / 2) + _EPS or abs(t0 - t1) > _EPS
                or not _EPS < abs(w0) <= .25 + _EPS or abs(w0 + w1) > _EPS
                or any(_polygon_overlaps_box(vertices, target.get("path_bbox", target["bbox"])) for target in targets)):
            return None
        points.extend(vertices)
    return [min(v[0] for v in points) - radius, min(v[1] for v in points) - radius,
            max(v[0] for v in points) + radius, max(v[1] for v in points) + radius]


def check_frame(objects: list[dict], frame: int, config: dict, *, contacts=()) -> list[dict]:
    """Check one observed semantic frame against the documented record/config."""
    findings = []

    def error(code, ids, message, suggestion):
        findings.append({"code": code, "severity": "error", "frame": frame,
                         "object_ids": ids, "message": message, "suggestion": suggestion})

    if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
        error("invalid_frame", [], "frame must be a nonnegative integer", "Supply the final output frame index.")
        return findings
    if not isinstance(config, dict):
        error("invalid_config", [], "config must be a mapping", "Supply an empty mapping to use defaults.")
        return findings
    cfg = {**_DEFAULTS, **config}
    problems = []
    if set(config) - set(_DEFAULTS):
        problems.append("unknown config fields: " + ", ".join(map(str, set(config) - set(_DEFAULTS))))
    if not _box(cfg["viewport"], area=True):
        problems.append("viewport must be a positive-area finite bbox")
    if not _number(cfg["margin"]) or not .05 <= cfg["margin"] < .5:
        problems.append("margin must be a fraction >=.05 and <.5")
    for key in ("min_gap", "container_padding", "font_tolerance", "opacity_threshold"):
        if not _number(cfg[key]) or cfg[key] < 0:
            problems.append(f"{key} must be finite and nonnegative")
    for key in ("min_gap", "container_padding"):
        if _number(cfg[key]) and cfg[key] == 0:
            problems.append(f"{key} must be positive")
    if _number(cfg["opacity_threshold"]) and cfg["opacity_threshold"] > .01:
        problems.append("opacity_threshold must not exceed .01 (1% opacity)")
    if _number(cfg["font_tolerance"]) and cfg["font_tolerance"] > .1:
        problems.append("font_tolerance must not exceed .1 font units")
    try:
        validate_font_sizes(cfg["font_sizes"])
    except ValueError as exc:
        problems.append(str(exc))
    zone = cfg["subtitle_zone"]
    if zone is not None and not _box(zone, area=True):
        problems.append("subtitle_zone must be None or a positive-area finite bbox")
    if problems:
        for message in problems:
            error("invalid_config", [], message, "Correct the named config field before checking geometry.")
        return findings
    viewport = cfg["viewport"]
    width, height = viewport[2] - viewport[0], viewport[3] - viewport[1]
    xmargin = width * cfg["margin"]
    ymargin = height * cfg["margin"]
    safe = [viewport[0] + xmargin, viewport[1] + ymargin, viewport[2] - xmargin, viewport[3] - ymargin]
    if not all(_number(v) for v in (width, height, xmargin, ymargin)) or not _box(safe, area=True):
        error("invalid_config", [], "viewport derived dimensions and safe geometry must be finite and positive",
              "Use a viewport whose dimensions and safety margins remain finite.")
        return findings
    if zone is not None and not _contains(safe, zone):
        error("invalid_config", [], "subtitle_zone must stay inside safe viewport", "Move the subtitle zone inside the safety margin.")
        return findings
    if not isinstance(objects, list):
        error("invalid_objects", [], "objects must be a list of semantic records", "Include every observed foreground object, even unregistered ones.")
        return findings
    active, seen = {}, set()
    for index, record in enumerate(objects):
        label = f"objects[{index}]"
        if not isinstance(record, dict):
            error("invalid_object", [label], "object must be a mapping", "Supply the required semantic object fields.")
            continue
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            error("invalid_object", [label], "id must be a nonempty string", "Assign a stable semantic object ID.")
            continue
        if identifier in seen:
            error("duplicate_id", [identifier], "object ID appears twice in the same frame", "Record each semantic object exactly once.")
            continue
        seen.add(identifier)
        required = {"kind", "bbox", "visible", "registered", "parent", "role", "effective_font_size"}
        bad = list(sorted(required - set(record)))
        if not isinstance(record.get("kind"), str) or not record.get("kind"):
            bad.append("kind must be a nonempty string")
        if not _box(record.get("bbox")):
            bad.append("bbox must be finite left,bottom,right,top with ordered bounds")
        if any(key in record for key in ("path_bbox", "paint_radius", "inner_bbox")):
            path_box, radius = record.get("path_bbox"), record.get("paint_radius")
            if (not _box(path_box) or not _number(radius) or radius < 0
                    or not _box(record.get("bbox"))
                    or any(abs(a - b) > _EPS for a, b in zip(record["bbox"],
                        [path_box[0] - radius, path_box[1] - radius,
                         path_box[2] + radius, path_box[3] + radius]))):
                bad.append("painted bbox must enclose its observed path and paint radius")
            if "inner_bbox" in record:
                inner = record["inner_bbox"]
                if (not _box(path_box) or not _number(radius) or radius < 0 or not _box(inner)
                        or not _contains([path_box[0] + radius, path_box[1] + radius,
                                          path_box[2] - radius, path_box[3] - radius], inner)):
                    bad.append("container inner_bbox must be inset from its path by the paint radius")
        for key in ("visible", "registered"):
            if not isinstance(record.get(key), bool):
                bad.append(f"{key} must be boolean")
        if record.get("parent") is not None and (not isinstance(record["parent"], str) or not record["parent"]):
            bad.append("parent must be None or an object ID")
        if record.get("role") is not None and not isinstance(record["role"], str):
            bad.append("role must be None or a font role string")
        opacity = record.get("opacity", 1)
        if not _number(opacity) or not 0 <= opacity <= 1:
            bad.append("opacity must be finite in [0,1]")
        start, end = record.get("start_frame", 0), record.get("end_frame")
        valid_start = isinstance(start, int) and not isinstance(start, bool) and start >= 0
        if not valid_start:
            bad.append("start_frame must be a nonnegative integer")
        if end is not None and (not isinstance(end, int) or isinstance(end, bool)
                                or not valid_start or end <= start):
            bad.append("end_frame must be an integer greater than start_frame")
        if bad:
            error("invalid_object", [identifier], f"{label}: " + "; ".join(bad), "Correct the named object fields and repeat this frame.")
            continue
        if not record["visible"] or opacity <= cfg["opacity_threshold"] or frame < start or (end is not None and frame >= end):
            continue
        if record["kind"] == "background":
            if record["parent"] is None and _contains(record["bbox"], viewport):
                continue
            error("invalid_background", [identifier], "background must cover viewport and have no parent", "Use background only for the full-frame backing; register other shapes as foreground.")
        if not record["registered"]:
            error("unregistered", [identifier], "visible foreground was not registered", "Register the observed semantic object with a stable ID.")
        active[identifier] = record
        if not _contains(safe, record["bbox"]):
            error("safe_boundary", [identifier], "object extends outside the safe viewport", "Move/reflow the object inside the 5% safety boundary; do not shrink text.")
        if record["kind"] in _TEXT or record["role"] is not None or record["effective_font_size"] is not None:
            role, size = record["role"], record["effective_font_size"]
            if (role not in cfg["font_sizes"] or not _number(size)
                    or (record["kind"] == "formula" and role != "body")
                    or abs(size - cfg["font_sizes"].get(role, 0)) > cfg["font_tolerance"]):
                error("font_size", [identifier], "effective_font_size must equal its fixed title/body/caption role", "Use the assigned fixed role size after scaling; rewrite, wrap, or split long copy.")
        if record["kind"] == "subtitle":
            if zone is None or not _contains(zone, record["bbox"]):
                error("subtitle_zone", [identifier], "subtitle is outside its reserved zone", "Configure subtitle_zone and place subtitles completely inside it.")
        elif zone is not None and _near(record["bbox"], zone, cfg["min_gap"]):
            error("subtitle_zone", [identifier], "foreground intrudes on reserved subtitle zone", "Move chart/body content away from the subtitle region.")

    valid_parents = {}
    for identifier, record in active.items():
        parent_id = record["parent"]
        if parent_id is None:
            continue
        parent = active.get(parent_id)
        visited, cursor = {identifier}, parent_id
        cycle = False
        while cursor in active:
            if cursor in visited:
                cycle = True
                break
            visited.add(cursor)
            cursor = active[cursor]["parent"]
        if parent is None or parent["kind"] != "container" or not parent["registered"] or cycle:
            error("invalid_parent", [identifier, parent_id], "parent must be a visible registered container without cycles", "Correct the explicit parent ID and container hierarchy.")
        elif not _contains(parent.get("inner_bbox", parent["bbox"]), record["bbox"], cfg["container_padding"]):
            error("container_overflow", [identifier, parent_id], "child overflows container or lacks required padding", "Reflow child inside all four padded edges; do not shrink text.")
        else:
            valid_parents[identifier] = parent_id

    def related(a, b):
        cursor = a
        while cursor in valid_parents:
            cursor = valid_parents[cursor]
            if cursor == b:
                return True
        return False

    connector_targets = {}
    for identifier, record in active.items():
        if record["kind"] != "connector":
            continue
        endpoints = record.get("endpoints")
        targets = []
        valid = isinstance(endpoints, list) and len(endpoints) == 2
        if valid:
            for endpoint in endpoints:
                if not isinstance(endpoint, dict) or not isinstance(endpoint.get("object_id"), str):
                    valid = False
                    break
                target = active.get(endpoint["object_id"])
                point = endpoint.get("point")
                if (target is None or target["kind"] in _TEXT | {"connector", "background"}
                        or target["role"] is not None or not target["registered"]
                        or not isinstance(point, (list, tuple)) or len(point) != 2
                        or not all(_number(v) for v in point)
                        or target.get("paint_radius", 0) > .05
                        or not _boundary(point, target.get("path_bbox", target["bbox"]))
                        or not _contains(record["bbox"], [*point, *point])):
                    valid = False
                    break
                targets.append(target)
        if valid:
            envelope = _connector_envelope(record, endpoints, targets)
            valid = (envelope is not None and all(abs(v - w) <= _EPS for v, w in zip(record["bbox"], envelope))
                     and targets[0]["id"] != targets[1]["id"]
                     and all(_leaves(endpoints[i]["point"], endpoints[1 - i]["point"],
                         targets[i].get("path_bbox", targets[i]["bbox"])) for i in (0, 1)))
        if not valid:
            error("invalid_connector", [identifier], "connector needs valid node-boundary endpoints, narrow observed tips/stroke and a matching bbox", "Supply two {object_id,point:[x,y]} endpoints; optional tips/stroke_radius must match actual geometry without entering node interiors.")
        else:
            connector_targets[identifier] = {target["id"] for target in targets}
    contact_findings, contact_pairs = validate_contacts(list(active.values()), frame, contacts)
    findings.extend(contact_findings)
    records = list(active.values())
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            aid, bid = a["id"], b["id"]
            if (related(aid, bid) or related(bid, aid)
                    or tuple(sorted((aid, bid))) in contact_pairs
                    or bid in connector_targets.get(aid, ()) or aid in connector_targets.get(bid, ())):
                continue
            if _near(a["bbox"], b["bbox"], cfg["min_gap"]):
                error("collision", [aid, bid], "semantic bounding boxes overlap or lack required separation", "Move/reflow objects apart, or add a specific valid container/endpoint relationship.")
    return findings

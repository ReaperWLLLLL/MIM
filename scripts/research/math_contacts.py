"""Fail-closed permissions for two mathematical contacts, never generic overlap.

Geometry is observed by ResearchScene, not supplied to track(): straight-line
endpoints, a canonical circular path's center/radius, or axis-aligned rectangle
bounds. Its envelope MUST agree with path_bbox and bbox + actual paint_radius.
All comparisons use 1e-8 scene units, independent of the visual safety gap.
Inactive half-open declarations grant nothing (and need not have objects yet).
"""
from __future__ import annotations

import math

EPS = 1e-8
KINDS = {"point_on_number_line", "adjacent_weight_segments"}


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _vector(value, size):
    return isinstance(value, (list, tuple)) and len(value) == size and all(_number(x) for x in value)


def declaration_error(contact):
    """Shared declaration contract for the scene API and pure frame validator."""
    if not isinstance(contact, dict) or set(contact) != {"id", "kind", "objects", "start_frame", "end_frame"}:
        return "contact requires exactly id, kind, objects, start_frame and end_frame"
    if not isinstance(contact["id"], str) or not contact["id"]:
        return "contact id must be a nonempty string"
    if not isinstance(contact["kind"], str) or contact["kind"] not in KINDS:
        return "unsupported mathematical contact kind"
    ids = contact["objects"]
    if (not isinstance(ids, (tuple, list)) or len(ids) != 2
            or any(not isinstance(x, str) or not x for x in ids) or ids[0] == ids[1]):
        return "contact must name exactly two distinct semantic object IDs"
    start, end = contact["start_frame"], contact["end_frame"]
    if (not isinstance(start, int) or isinstance(start, bool) or start < 0
            or not isinstance(end, int) or isinstance(end, bool) or end <= start):
        return "contact requires a nonnegative half-open integer frame interval"
    return None


def duplicate_contact(a, b):
    return (a["id"] == b["id"] or (set(a["objects"]) == set(b["objects"])
            and max(a["start_frame"], b["start_frame"]) < min(a["end_frame"], b["end_frame"])))


def _geometry(record, frame):
    """Validate observed geometry + paint envelope; never infer from a bbox."""
    if (record.get("registered") is not True or record.get("visible") is not True
            or not isinstance(record.get("kind"), str)
            or record["kind"] in {"text", "formula", "subtitle", "background", "container", "connector"}
            or record.get("role") is not None or record.get("effective_font_size") is not None):
        return None
    opacity = record.get("opacity", 1)
    start, end = record.get("start_frame", 0), record.get("end_frame")
    if (not _number(opacity) or not .01 < opacity <= 1
            or not isinstance(start, int) or isinstance(start, bool) or start < 0 or frame < start
            or (end is not None and (not isinstance(end, int) or isinstance(end, bool) or end <= start or frame >= end))):
        return None
    geo, paint = record.get("geometry"), record.get("paint_radius")
    if not isinstance(geo, dict) or not _number(paint) or not 0 <= paint <= .05:
        return None
    kind = geo.get("type")
    if kind == "line":
        ends = geo.get("endpoints")
        if not isinstance(ends, (list, tuple)) or len(ends) != 2 or not all(_vector(p, 2) for p in ends):
            return None
        a, b = ends
        length = math.hypot(b[0]-a[0], b[1]-a[1])
        if not _number(length) or length <= EPS:
            return None
        box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
    elif kind == "circle":
        center, radius = geo.get("center"), geo.get("radius")
        if not _vector(center, 2) or not _number(radius) or not EPS < radius <= .1 + EPS:
            return None
        x, y = center
        box = [x-radius, y-radius, x+radius, y+radius]
    elif kind == "rectangle":
        box = geo.get("bounds")
        if not _vector(box, 4) or box[2]-box[0] <= EPS or box[3]-box[1] <= EPS:
            return None
    else:
        return None
    expected = [box[0]-paint, box[1]-paint, box[2]+paint, box[3]+paint]
    if (not all(_number(x) for x in expected)
            or not _vector(record.get("path_bbox"), 4) or not _vector(record.get("bbox"), 4)
            or any(abs(x-y) > EPS for x, y in zip(record["path_bbox"], box))
            or any(abs(x-y) > EPS for x, y in zip(record["bbox"], expected))):
        return None
    return geo


def _valid_relation(kind, a, b):
    if kind == "point_on_number_line":
        if a["type"] == "circle" and b["type"] == "line":
            a, b = b, a
        if a["type"] != "line" or b["type"] != "circle":
            return False
        p, q = a["endpoints"]
        length = math.hypot(q[0]-p[0], q[1]-p[1])
        ux, uy = (q[0]-p[0])/length, (q[1]-p[1])/length
        dx, dy = b["center"][0]-p[0], b["center"][1]-p[1]
        along, perpendicular = dx*ux+dy*uy, dx*uy-dy*ux
        return (all(_number(x) for x in (along, perpendicular))
                and -EPS <= along <= length+EPS and abs(perpendicular) <= EPS)
    if a["type"] != "rectangle" or b["type"] != "rectangle":
        return False
    a, b = sorted((a["bounds"], b["bounds"]), key=lambda box: box[0])
    # Matching nonzero height, shared full vertical edge, no interior overlap.
    # Envelope checks bound the painted intersection to [edge-r_b,edge+r_a].
    return abs(a[2]-b[0]) <= EPS and abs(a[1]-b[1]) <= EPS and abs(a[3]-b[3]) <= EPS


def validate_contacts(objects: list[dict], frame: int, contacts: list[dict]) -> tuple[list[dict], set[tuple[str, str]]]:
    findings, pairs = [], set()

    def error(ids, message):
        findings.append({"code": "invalid_math_contact", "severity": "error", "frame": frame,
                         "object_ids": ids, "message": message,
                         "suggestion": "Declare only the supported pair and interval; use observed narrow geometry, never overlap/text exemptions."})

    if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
        error([], "contact frame must be a nonnegative integer")
        return findings, pairs
    if not isinstance(contacts, (list, tuple)) or not isinstance(objects, list):
        error([], "contacts must be a list of declarations and objects a list of observed records")
        return findings, pairs
    declarations = []
    for contact in contacts:
        problem = declaration_error(contact)
        if problem:
            error([], problem)
        else:
            declarations.append(contact)
    duplicates = set()
    for i, a in enumerate(declarations):
        for j in range(i+1, len(declarations)):
            if duplicate_contact(a, declarations[j]):
                duplicates.update((i, j))
    by_id, duplicate_ids = {}, set()
    for record in objects:
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            if record["id"] in by_id:
                duplicate_ids.add(record["id"])
            by_id[record["id"]] = record
    for i, contact in enumerate(declarations):
        ids = list(contact["objects"])
        if i in duplicates:
            error(ids, f"duplicate contact id or overlapping pair interval: {contact['id']}")
            continue
        if not contact["start_frame"] <= frame < contact["end_frame"]:
            continue
        if any(x not in by_id or x in duplicate_ids for x in ids):
            error(ids, f"contact {contact['id']} needs two unique observed objects")
            continue
        geometry = [_geometry(by_id[x], frame) for x in ids]
        if any(g is None for g in geometry) or not _valid_relation(contact["kind"], *geometry):
            error(ids, f"contact {contact['id']} does not match eligible observed geometry and narrow paint")
            continue
        pairs.add(tuple(sorted(ids)))
    return findings, pairs

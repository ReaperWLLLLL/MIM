"""Cairo + Manim Slides runtime with semantic audit of EVERY emitted frame.

Subclass ResearchScene and call beat() exactly once per frozen beat, in order.
text(key, role) uses final screen_text; register other semantic shapes with track.
For straight lines/arrows use track(..., kind='connector', endpoints=(id0,id1)).
Containers must be actual boundaries; grouping is not a collision exemption.
Fade/translation is supported; text-changing Transform is deliberately rejected:
use distinct registered Text objects with FadeOut/FadeIn, not glyph morphs.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re

import av
import cairo
import manimpango
import numpy as np
from PIL import Image
from manim import ArrowTip, Circle, Line, Rectangle, ManimColor, MarkupText, Text, Tex, Transform, config
from manim.animation.animation import prepare_animation
from manim.camera.camera import Camera, LINE_JOIN_MAP, CAP_STYLE_MAP
from manim.constants import LineJointType, CapStyleType
from manim.mobject.svg.svg_mobject import VMobjectFromSVGPath
from manim.renderer.cairo_renderer import CairoRenderer
from manim.scene.scene_file_writer import SceneFileWriter
from manim_slides import Slide
from manim_slides.config import PresentationConfig, SlideConfig

from .layout import check_frame
from .math_contacts import EPS, declaration_error, duplicate_contact
from .themes import validate_font_sizes

FONT = "Microsoft YaHei"
FONT_SIZES = {"title": 48, "body": 30, "caption": 20}
LAYOUT = {"viewport": [-64 / 9, -4, 64 / 9, 4], "margin": .05, "min_gap": .1,
          "container_padding": .15, "font_sizes": FONT_SIZES,
          "font_tolerance": .01, "subtitle_zone": None, "opacity_threshold": .01}
_TEXT_TYPES = (Text, MarkupText, Tex)
_REGISTERED_FONTS = set()


def ensure_font(font_file=None):
    """Register a locally licensed font in THIS process, never copy/download it."""
    path = font_file or os.environ.get("RESEARCH_FONT_FILE")
    if path is None:
        candidate = Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts/msyh.ttc")
        if candidate.is_file():
            path = candidate
    if path:
        path = str(Path(path).resolve())
        if path not in _REGISTERED_FONTS:
            if not manimpango.register_font(path):
                raise ValueError(f"could not register local font: {path}")
            _REGISTERED_FONTS.add(path)
    if FONT not in manimpango.list_fonts():
        raise ValueError(f"{FONT} unavailable; provide a licensed local --font-file")
    return {"family": FONT, "file": str(Path(path).resolve()) if path else None,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None}


class AuditFailure(RuntimeError):
    pass


class _AuditedFileWriter(SceneFileWriter):
    def combine_files(self, input_files, output_file, create_gif=False, includes_sound=False):
        if create_gif or includes_sound:
            raise ValueError("audited masters require silent MP4 partials")
        # Manim/PyAV partial headers can shorten an exact 11-frame clip by five
        # track ticks. The concat demuxer otherwise shifts every later frame.
        # Supply frame-derived durations; stream-copy the original encoded bytes.
        entries = []
        for path in input_files:
            with av.open(str(path)) as clip:
                frames = clip.streams.video[0].frames
            duration = Fraction(frames, config.frame_rate)
            # Native partial names are generated tokens. Keep the caller's
            # directory entirely out of ffconcat's quoting grammar.
            relative = Path(path).resolve().relative_to(self.partial_movie_directory.resolve())
            if len(relative.parts) != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]+", relative.name):
                raise ValueError("native partial must have a generated safe filename")
            entries.extend([f"file '{relative.name}'", f"duration {float(duration):.12f}"])
        file_list = self.partial_movie_directory / "audited_partial_movie_file_list.txt"
        file_list.write_text("\n".join(entries) + "\n", encoding="utf-8")
        with av.open(str(file_list), format="concat", options={"safe": "0", "an": "1"}) as source:
            with av.open(str(output_file), mode="w") as destination:
                stream = source.streams.video[0]
                target = destination.add_stream_from_template(stream)
                for packet in source.demux(stream):
                    if packet.dts is not None:
                        packet.dts = None
                        packet.stream = target
                        destination.mux(packet)


class _AuditedRenderer(CairoRenderer):
    def add_frame(self, frame, num_frames=1):
        if not self.skip_animations:
            for _ in range(num_frames):
                self.owner.capture_frame(frame)
        super().add_frame(frame, num_frames=num_frames)

    def freeze_current_frame(self, duration):
        # Cairo's int(duration / dt) can lose a frame to binary float rounding.
        frames = round(duration * self.camera.frame_rate)
        if abs(duration * self.camera.frame_rate - frames) > 1e-7:
            raise ValueError("frozen hold duration must be an integer number of frames")
        self.add_frame(self.get_frame(), num_frames=frames)


class _AuditedCamera(Camera):
    def apply_stroke(self, ctx, vmobject, background=False):
        result = super().apply_stroke(ctx, vmobject, background)
        # AUTO inherits Cairo context state, including another object's cap/join.
        # Observe the real drawing context, not an assumed default formula.
        if not hasattr(self, "stroke_contexts"):
            self.stroke_contexts = {}
        self.stroke_contexts[(id(vmobject), background)] = (
            ctx.get_matrix(), ctx.get_line_join(), ctx.get_line_cap(), ctx.get_miter_limit())
        return result

    def painted_radius(self, mob, opacity_threshold):
        if not mob.has_points() or not hasattr(mob, "get_stroke_width"):
            return 0.0
        low, high = np.min(mob.points, axis=0), np.max(mob.points, axis=0)
        radius = 0.0
        for background in (True, False):
            width = float(mob.get_stroke_width(background))
            if width <= 0 or np.max(self.get_stroke_rgbas(mob, background)[:, 3]) <= opacity_threshold:
                continue
            ctx = cairo.Context(cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None))
            observed = getattr(self, "stroke_contexts", {}).get((id(mob), background))
            if observed:
                matrix, join, cap, limit = observed
                ctx.set_matrix(matrix)
                ctx.set_line_join(join)
                ctx.set_line_cap(cap)
                ctx.set_miter_limit(limit)
            else:
                # Pre-render observations use the same camera scale. Explicit
                # joins/caps override it just as in Camera.apply_stroke.
                ctx.set_matrix(cairo.Matrix(self.pixel_width / self.frame_width, 0, 0,
                                            -self.pixel_height / self.frame_height))
            if mob.joint_type != LineJointType.AUTO:
                ctx.set_line_join(LINE_JOIN_MAP[mob.joint_type])
            if mob.cap_style != CapStyleType.AUTO:
                ctx.set_line_cap(CAP_STYLE_MAP[mob.cap_style])
            self.set_cairo_context_path(ctx, mob)
            scene_width = width * self.cairo_line_width_multiple
            ctx.set_line_width(scene_width)
            x0, y0, x1, y1 = ctx.stroke_extents()
            # Extents include actual miter/square/round geometry. Uniformly
            # expanding the control-point hull is conservative, including tips.
            radius = max(radius, scene_width / 2, low[0] - x0, low[1] - y0,
                         x1 - high[0], y1 - high[1])
        return float(radius)


class ResearchScene(Slide):
    def _save_slides(self, use_cache=True, flush_cache=False, skip_reversing=False):
        """Keep native metadata, using the audited path-safe partial concat.

        Research masters are forward-only videos; imported external slide media
        cannot have the required per-frame observations.
        """
        if not skip_reversing:
            raise ValueError("audited research slides require skip_reversing")
        self._add_last_slide()
        folder = self._output_folder / "files" / str(self)
        folder.mkdir(parents=True, exist_ok=True)
        slides = []
        for index, config_item in enumerate(self._slides):
            if config_item.skip_animations:
                continue
            if config_item.src:
                raise ValueError("external native slide media lacks frame audit")
            target = folder / f"slide-{index:04d}.mp4"
            self.renderer.file_writer.combine_files(
                self._partial_movie_files[config_item.slides_slice], target)
            slides.append(SlideConfig.from_pre_slide_config_and_files(config_item, target, target))
        PresentationConfig(slides=slides, resolution=self._resolution,
            background_color=self._background_color).to_file(self._output_folder / f"{self}.json")

    def __init__(self, *, spec, timeline, slide_id, theme, audit_dir, layout=None, **kwargs):
        if theme["font_family"] != FONT:
            raise ValueError("research scenes require Microsoft YaHei")
        self.font_sizes = validate_font_sizes(theme["font_sizes"])
        if config.renderer.value != "cairo" or not config.disable_caching:
            raise ValueError("audited rendering requires Cairo with disable_caching=True")
        self.spec, self.timeline, self.theme = spec, timeline, theme
        self.slide_spec = next(s for s in spec["slides"] if s["id"] == slide_id)
        self.slide_timing = next(s for s in timeline["slides"] if s["id"] == slide_id)
        self.fps = timeline["fps"]
        if config.frame_rate != self.fps:
            raise ValueError("renderer fps differs from frozen timeline")
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.layout = {**LAYOUT, "font_sizes": dict(self.font_sizes), **(layout or {})}
        actual_viewport = [-config.frame_width / 2, -config.frame_height / 2,
                           config.frame_width / 2, config.frame_height / 2]
        if (self.layout["font_sizes"] != self.font_sizes
                or not np.allclose(self.layout["viewport"], actual_viewport, atol=1e-10, rtol=0)
                or check_frame([], 0, self.layout)):
            raise ValueError("layout must match actual viewport, fixed font roles and validated safety constraints")
        self._registry, self._identities = {}, {}
        self._math_contacts = []
        self._frame_count, self._beat_index = 0, 0
        self._findings, self._beat_log = [], []
        self._trace = None
        self._screenshot_written = False
        renderer = self._make_renderer()
        super().__init__(renderer=renderer, **kwargs)
        renderer.owner = self
        self.camera.background_color = ManimColor(theme["colors"]["background"])

    def _make_renderer(self) -> CairoRenderer:
        return _AuditedRenderer(file_writer_class=_AuditedFileWriter, camera_class=_AuditedCamera)

    def track(self, id, mobject, kind, parent=None, role=None, *, endpoints=None):
        """Register identity, never infer containment or promote group children."""
        if not isinstance(id, str) or not id or id in self._registry or id_builtin(mobject) in self._identities:
            raise ValueError("semantic IDs and mobject registrations must be unique")
        if role is not None and role not in self.font_sizes:
            raise ValueError("unknown font role")
        if isinstance(mobject, _TEXT_TYPES) and kind not in {"text", "formula", "subtitle"}:
            raise ValueError("text cannot be registered as a decorative shape")
        record = {"id": id, "kind": kind, "parent": parent, "role": role,
                  "endpoints": endpoints, "mobject": mobject}
        # Retain the original object: an integer Python id may be recycled after
        # FadeOut removes the last scene reference. Never register a later stranger.
        self._registry[id] = record
        self._identities[id_builtin(mobject)] = id
        if isinstance(mobject, _TEXT_TYPES):
            # Pango's chars contains the constructor's glyph objects, not later
            # .add(...) descendants. Keep references so Manim deepcopy preserves
            # their identities within animation targets; never exempt a subtree.
            mobject._research_glyphs = self._glyphs(mobject)
        # Manim's .animate target is a deep copy; this token preserves its semantic
        # identity during preflight only. Actual scene coverage uses identity map.
        mobject._research_id = id
        return mobject

    def text(self, key, role="body", **kwargs):
        if key not in self.slide_spec["screen_text"]:
            raise ValueError(f"unknown screen_text key: {key}")
        if role not in self.font_sizes:
            raise ValueError(f"unknown font role: {role}")
        if any(k in kwargs for k in ("font", "font_size", "t2f", "t2s", "text", "height", "width")):
            raise ValueError("font and text geometry cannot override fixed roles")
        parent = kwargs.pop("parent", None)
        kwargs.setdefault("color", self.theme["colors"]["foreground"])
        text = Text(self.slide_spec["screen_text"][key], font=FONT,
                    font_size=self.font_sizes[role], **kwargs)
        return self.track(f"text:{key}", text, "text", role=role, parent=parent)

    def math_contact(self, id: str, *, kind: str, objects: tuple[str, str],
                     start_frame: int, end_frame: int) -> None:
        """Declare a pair, never its geometry; each emitted frame rechecks it."""
        contact = {"id": id, "kind": kind, "objects": objects,
                   "start_frame": start_frame, "end_frame": end_frame}
        problem = declaration_error(contact)
        if problem or any(duplicate_contact(contact, old) for old in self._math_contacts):
            raise ValueError(problem or "duplicate contact id or overlapping pair interval")
        self._math_contacts.append({**contact, "objects": list(objects)})

    def _metadata(self, mob, allow_copy=False):
        key = self._identities.get(id_builtin(mob))
        if key is None and allow_copy:
            key = getattr(mob, "_research_id", None)
        return self._registry.get(key)

    @staticmethod
    def _glyphs(mob):
        captured = getattr(mob, "_research_glyphs", None)
        if captured is not None:
            return captured
        if isinstance(mob, (Text, MarkupText)):
            return tuple(mob.chars.submobjects)
        # Tex has no Pango chars index. Its imported SVG path leaves are glyphs;
        # ordinary attached Manim shapes are not SVG glyph components.
        return tuple(part for part in mob.get_family()[1:] if isinstance(part, VMobjectFromSVGPath))

    def _semantic(self, roots):
        """Atomic Text/shape geometry, but always descend into semantic children.

        Text owns its glyphs; arrows own their actual tip components. Other
        shape children are independent foreground, even under a tracked shape.
        Pointless VGroups are traversal-only: tracking one cannot register children.
        """
        seen = set()

        def walk(mob, components=frozenset()):
            if id_builtin(mob) in seen:
                return
            seen.add(id_builtin(mob))
            text = isinstance(mob, _TEXT_TYPES)
            own = bool(mob.has_points()) or text
            semantic = own and (id_builtin(mob) not in components or text or id_builtin(mob) in self._identities)
            if semantic:
                yield mob
            if text:
                components = components | {id_builtin(glyph) for glyph in self._glyphs(mob)}
            for child in mob.submobjects:
                tip = (isinstance(child, ArrowTip) and
                       (child is getattr(mob, "tip", None) or child is getattr(mob, "start_tip", None)))
                yield from walk(child, components | {id_builtin(child)} if tip else components)
        for root in roots:
            yield from walk(root)

    @staticmethod
    def _opacity(mob, include_children, *, parts=None):
        values = []
        if parts is None:
            parts = mob.get_family() if include_children else [mob]
        for part in parts:
            if part.has_points():
                for name, width in (("fill_rgbas", None), ("stroke_rgbas", "stroke_width"),
                                    ("background_stroke_rgbas", "background_stroke_width")):
                    rgba = getattr(part, name, None)
                    if (rgba is not None and len(rgba)
                            and (width is None or np.max(getattr(part, width, 0)) > 0)):
                        values.extend(np.asarray(rgba)[:, 3])
            # ImageMobject stores alpha in its pixel array.
            pixels = getattr(part, "pixel_array", None)
            if pixels is not None and pixels.shape[-1] == 4:
                values.append(float(np.max(pixels[:, :, 3])) / 255)
        return float(max(values, default=0))

    @staticmethod
    def _source_text(mob):
        # Manim 0.20 Text.text is a glyph-index string: tabs are expanded and
        # spaces/newlines removed. original_text retains the constructor input.
        # Compare that exact source, never normalized copy or registration data.
        if isinstance(mob, Text):
            return mob.original_text
        return getattr(mob, "text", getattr(mob, "tex_string", ""))

    @staticmethod
    def _contact_geometry(mob):
        """Recognize supported paths from ALL cubic controls, not class/getters.

        Conservatively reject extra components, nonplanar/deformed paths and
        unsupported subdivisions. Circle evidence requires regular canonical
        circular Beziers and a control hull matching center +/- radius; rotated
        circles with a wider control hull remain unsupported, not exempted.
        """
        if not isinstance(mob, (Line, Circle, Rectangle)) or mob.submobjects:
            return None
        points = np.asarray(mob.points)
        if (points.ndim != 2 or points.shape[1] != 3 or not len(points) or len(points) % 4
                or not np.isfinite(points).all() or np.ptp(points[:, 2]) > EPS):
            return None
        curves = points[:, :2].reshape(-1, 4, 2)
        if len(curves) > 1 and not np.allclose(curves[:-1, 3], curves[1:, 0], atol=EPS, rtol=0):
            return None

        def straight(curve):
            p, q = curve[0], curve[3]
            length = np.linalg.norm(q-p)
            if length <= EPS:
                return False
            unit = (q-p)/length
            along = (curve-p) @ unit
            cross = (curve[:, 0]-p[0])*unit[1] - (curve[:, 1]-p[1])*unit[0]
            return (np.max(np.abs(cross)) <= EPS and np.min(along) >= -EPS
                    and np.max(along) <= length+EPS and np.min(np.diff(along)) >= -EPS)

        if isinstance(mob, Line):
            # The entire path, not just get_start/get_end, must be one segment.
            flat = points[:, :2]
            if not straight(np.array([flat[0], flat[0], flat[-1], flat[-1]])):
                return None
            unit = (flat[-1]-flat[0])/np.linalg.norm(flat[-1]-flat[0])
            along = (flat-flat[0]) @ unit
            cross = (flat[:, 0]-flat[0, 0])*unit[1] - (flat[:, 1]-flat[0, 1])*unit[0]
            if (np.max(np.abs(cross)) > EPS or np.min(np.diff(along)) < -EPS
                    or np.min(along) < -EPS or np.max(along) > along[-1]+EPS):
                return None
            return {"type": "line", "endpoints": [flat[0].tolist(), flat[-1].tolist()]}
        if not np.allclose(curves[-1, 3], curves[0, 0], atol=EPS, rtol=0):
            return None
        low, high = np.min(points[:, :2], axis=0), np.max(points[:, :2], axis=0)
        if isinstance(mob, Rectangle):
            if len(curves) != 4 or np.min(high-low) <= EPS or not all(straight(c) for c in curves):
                return None
            corners = {(float(x), float(y)) for x in (low[0], high[0]) for y in (low[1], high[1])}
            anchors = curves[:, 0]
            if (len({tuple(p) for p in anchors}) != 4
                    or any(not any(np.allclose(p, c, atol=EPS, rtol=0) for c in corners) for p in anchors)
                    or any(min(abs(c[3, 0]-c[0, 0]), abs(c[3, 1]-c[0, 1])) > EPS for c in curves)):
                return None
            return {"type": "rectangle", "bounds": [*low.tolist(), *high.tolist()]}
        # Regular full-circle cubic construction: each handle must have the
        # analytic tangent direction and length, so an altered handle fails.
        count = len(curves)
        if count < 4:
            return None
        center = np.mean(curves[:, 0], axis=0)
        radius = np.linalg.norm(curves[0, 0]-center)
        if radius <= EPS:
            return None
        a, b = curves[0, 0]-center, curves[0, 3]-center
        direction = 1 if a[0]*b[1]-a[1]*b[0] > 0 else -1
        theta = direction*2*np.pi/count
        handle = 4/3*np.tan(theta/4)
        rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        for curve in curves:
            a, b = curve[0]-center, curve[3]-center
            expected = np.array([center+a, center+a+handle*np.array([-a[1], a[0]]),
                                 center+b-handle*np.array([-b[1], b[0]]), center+b])
            if (abs(np.linalg.norm(a)-radius) > EPS or not np.allclose(rotation @ a, b, atol=EPS, rtol=0)
                    or not np.allclose(curve, expected, atol=EPS, rtol=0)):
                return None
        if not np.allclose([*low, *high], [*(center-radius), *(center+radius)], atol=EPS, rtol=0):
            return None
        return {"type": "circle", "center": center.tolist(), "radius": float(radius)}

    def _record(self, mob, *, allow_copy=False):
        meta = self._metadata(mob, allow_copy)
        text = isinstance(mob, _TEXT_TYPES)
        include_children = text or bool(meta and meta["kind"] == "connector") or any(
            isinstance(getattr(mob, name, None), ArrowTip) for name in ("tip", "start_tip"))
        glyphs = None
        if text:
            observed_ids = {id_builtin(part) for part in mob.get_family()}
            glyphs = [part for part in self._glyphs(mob)
                      if id_builtin(part) in observed_ids and part.has_points()]
            if not glyphs:
                raise ValueError("text has no recognized visible glyph geometry")
            points = np.concatenate([part.points for part in glyphs])
        else:
            points = mob.get_all_points() if include_children else mob.points
        low, high = np.min(points, axis=0), np.max(points, axis=0)
        opacity = self._opacity(mob, include_children, parts=glyphs)
        # Text.font_size uses aggregate height, which includes arbitrary added
        # children. Normalize to glyph-only height so a child cannot mask scaling.
        font_size = (float(mob.font_size) * float(high[1] - low[1]) / mob.height
                     if text and mob.height else (0.0 if text else None))
        parts = glyphs if text else (mob.get_family() if include_children else [mob])
        radius = max((self.camera.painted_radius(part, self.layout["opacity_threshold"])
                      for part in parts), default=0)
        path_box = [float(low[0]), float(low[1]), float(high[0]), float(high[1])]
        record = {"id": meta["id"] if meta else f"unregistered:{type(mob).__name__}:{id_builtin(mob)}",
                  "kind": meta["kind"] if meta else ("text" if text else "shape"),
                  "bbox": [path_box[0] - radius, path_box[1] - radius,
                           path_box[2] + radius, path_box[3] + radius],
                  "path_bbox": path_box, "paint_radius": radius,
                  "visible": opacity > self.layout["opacity_threshold"], "opacity": opacity,
                  "registered": meta is not None, "parent": meta["parent"] if meta else None,
                  "role": meta["role"] if meta else None,
                  "effective_font_size": font_size}
        if meta and meta["kind"] == "container":
            record["inner_bbox"] = [path_box[0] + radius, path_box[1] + radius,
                                    path_box[2] - radius, path_box[3] - radius]
        if text:
            record["text"] = self._source_text(mob)
            record["font_family"] = getattr(mob, "font", None)
        else:
            geometry = self._contact_geometry(mob)
            if geometry is not None:
                record["geometry"] = geometry
        if meta and meta["kind"] == "connector":
            ids = meta["endpoints"] or (None, None)
            record["endpoints"] = [{"object_id": target, "point": [float(p[0]), float(p[1])]}
                for target, p in zip(ids, (mob.get_start(), mob.get_end()))]
            record["tips"] = []
            for name, endpoint in (("start_tip", 0), ("tip", 1)):
                tip = getattr(mob, name, None)
                if tip is not None and tip in mob.submobjects:
                    record["tips"].append({"endpoint": endpoint,
                        "vertices": [[float(p[0]), float(p[1])] for p in tip.get_vertices()]})
            record["stroke_radius"] = radius
        return record

    def observed_objects(self):
        return [self._record(mob) for mob in self._semantic([*self.mobjects, *self.foreground_mobjects])]

    def _finding(self, code, ids, message, phase="frame"):
        return {"code": code, "severity": "error", "frame": self.slide_timing["start_frame"] + self._frame_count,
                "local_frame": self._frame_count, "object_ids": ids, "message": message,
                "suggestion": "Use registered final copy, fixed font roles and explicit semantic geometry.", "phase": phase}

    def _copy_findings(self, records, phase="frame"):
        findings = []
        for record in records:
            if "text" not in record:
                continue
            if record["text"] not in self.slide_spec["screen_text"].values():
                findings.append(self._finding("screen_text", [record["id"]], "visible text is absent from slide.screen_text", phase))
            if record["kind"] != "formula" and record["font_family"] != FONT:
                findings.append(self._finding("font_family", [record["id"]], f"text must use {FONT}", phase))
        return findings

    def check_animations(self, animations):
        """Inspect actual sources and targets, including never-added Transform targets."""
        findings = []
        for raw in animations:
            animation = prepare_animation(raw)
            if hasattr(animation, "animations"):
                findings.extend(self.check_animations(animation.animations))
                continue
            roots = [(animation.mobject, False)]
            if isinstance(animation, Transform):
                target = animation.create_target()
                roots.append((target, True))
                source_text = [self._source_text(m)
                               for m in self._semantic([animation.mobject]) if isinstance(m, _TEXT_TYPES)]
                target_text = [self._source_text(m)
                               for m in self._semantic([target]) if isinstance(m, _TEXT_TYPES)]
                if source_text != target_text:
                    findings.append(self._finding("text_transform", [], "text-changing Transform is unsupported; use registered FadeOut/FadeIn", "animation"))
            for root, allow_copy in roots:
                if root is None:
                    continue
                records = [self._record(m, allow_copy=allow_copy) for m in self._semantic([root])]
                for record in records:
                    if not record["registered"]:
                        findings.append(self._finding("unregistered", [record["id"]], "animation source/target is not registered", "animation"))
                findings.extend(self._copy_findings(records, "animation"))
        return findings

    def _frame_evidence(self):
        """Optional evidence prepared before rasterization; ordinary scenes add none."""
        return {}

    def capture_frame(self, pixels):
        records = self.observed_objects()
        global_frame = self.slide_timing["start_frame"] + self._frame_count
        findings = check_frame(records, global_frame, self.layout, contacts=self._math_contacts) + self._copy_findings(records)
        for finding in findings:
            finding.setdefault("local_frame", self._frame_count)
        self._findings.extend(findings)
        if self._trace is None:
            raise AuditFailure("frame emitted outside audited render lifecycle")
        self._trace.write(json.dumps({"frame": global_frame, "local_frame": self._frame_count,
            "objects": records, "math_contacts": self._math_contacts, **self._frame_evidence(),
            "findings": findings}, ensure_ascii=False, allow_nan=False) + "\n")
        if self._findings and not self._screenshot_written:
            Image.fromarray(pixels).save(self.audit_dir / f"failure-frame-{self._frame_count:06d}.png")
            self._screenshot_written = True
        self._frame_count += 1

    def play(self, *animations, **kwargs):
        animations = [prepare_animation(a) for a in animations]
        self._findings.extend(self.check_animations(animations))
        return super().play(*animations, **kwargs)

    def beat(self, beat_id, animations, run_time):
        beats = self.slide_timing["beats"]
        if self._beat_index >= len(beats) or beats[self._beat_index]["id"] != beat_id:
            raise ValueError("beat order differs from frozen timeline")
        timing = beats[self._beat_index]
        if self._frame_count != timing["local_start_frame"]:
            raise ValueError("frames emitted outside frozen beat boundaries")
        if not isinstance(run_time, (int, float)) or isinstance(run_time, bool) or not math.isfinite(run_time) or run_time < 0:
            raise ValueError("run_time must be finite and nonnegative")
        requested = int((Decimal(str(run_time)) * self.fps).to_integral_value(rounding=ROUND_CEILING))
        if requested > timing["frames"] or (animations and requested == 0):
            raise ValueError("animation does not fit frozen audio beat; rewrite/split instead of shortening voice")
        animations = [prepare_animation(a) for a in animations]
        before = self._frame_count
        if animations:
            # nextafter prevents np.arange emitting an extra endpoint frame.
            self.play(*animations, run_time=float(np.nextafter(requested / self.fps, 0)))
        played = self._frame_count - before
        remaining = timing["frames"] - played
        if remaining < 0:
            raise ValueError("Manim emitted more animation frames than the frozen beat permits")
        if remaining:
            self.wait(remaining / self.fps, frozen_frame=True)
        if self._frame_count != timing["local_end_frame"]:
            raise ValueError("rendered beat frame count differs from frozen timeline")
        self._beat_log.append({"id": beat_id, "animation_frames": played, "wait_frames": remaining,
                               "start_frame": before, "end_frame": self._frame_count})
        self._beat_index += 1

    def render(self, *args, **kwargs):
        error = None
        with (self.audit_dir / "frames.jsonl").open("w", encoding="utf-8") as self._trace:
            try:
                self.next_slide(notes=self.slide_spec.get("notes", ""))
                super().render(*args, **kwargs)
                if self._beat_index != len(self.slide_timing["beats"]) or self._frame_count != self.slide_timing["frames"]:
                    raise ValueError("scene omitted beats or emitted an incorrect frame count")
            except Exception as exc:
                error = exc
            finally:
                report = {"ok": not self._findings and error is None, "timeline_hash": self.timeline["timeline_hash"],
                          "slide_id": self.slide_spec["id"], "fps": self.fps, "frames": self._frame_count,
                          "expected_frames": self.slide_timing["frames"], "layout": self.layout,
                          "math_contacts": self._math_contacts,
                          "theme": self.theme, "beats": self._beat_log, "findings": self._findings,
                          "error": str(error) if error else None}
                (self.audit_dir / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self._trace = None
        if error:
            raise error
        if self._findings:
            raise AuditFailure(f"{len(self._findings)} audit findings; see {self.audit_dir / 'qa.json'}")


# track's public parameter is named id; keep object identity unambiguous inside it.
id_builtin = id

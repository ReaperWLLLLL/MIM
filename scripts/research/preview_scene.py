"""Silent scalar previews: prepare canonical state BEFORE Cairo reads geometry.

Only numbers created by derived_number own this narrow, audited refresh path.
It does not authorize arbitrary text, glyph transforms or subtree exemptions.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import math

import numpy as np
from manim import Text, Wait, config
from tqdm import tqdm

from .scene import (FONT, ResearchScene, _AuditedCamera, _AuditedFileWriter,
                    _AuditedRenderer)


class _PreviewRenderer(_AuditedRenderer):
    def save_static_frame_data(self, scene, static_mobjects):
        # Cairo normally takes a pre-play snapshot. Preview state changes even
        # for objects Manim classified as static, so never capture/reuse it.
        self.static_image = None
        return None

    def update_frame(self, scene, mobjects=None, include_submobjects=True,
                     ignore_skipping=True, **kwargs):
        if self.skip_animations and not ignore_skipping:
            return
        scene._prepare_preview_frame()
        self.static_image = None
        # Ignore Manim's static/moving split; all live objects must be captured.
        return super().update_frame(scene, mobjects=None,
            include_submobjects=include_submobjects, ignore_skipping=ignore_skipping, **kwargs)


def _finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


class SilentPreviewScene(ResearchScene):
    """Subclass state_at(local_frame) and update_geometry(state), then preview_beat."""

    def __init__(self, **kwargs):
        timeline = kwargs.get("timeline", {})
        if (timeline.get("schema_version") != "research-preview-timeline-1"
                or timeline.get("mode") != "silent-preview"):
            raise ValueError("SilentPreviewScene requires a frozen silent-preview timeline")
        self._derived_numbers = {}
        self._math_state = {}
        self._preview_steps = None
        super().__init__(**kwargs)

    def _make_renderer(self):
        return _PreviewRenderer(file_writer_class=_AuditedFileWriter, camera_class=_AuditedCamera)

    def state_at(self, local_frame: int) -> dict[str, float]:
        raise NotImplementedError

    def update_geometry(self, state: dict[str, float]) -> None:
        raise NotImplementedError

    def _state(self):
        state = self.state_at(self._frame_count)
        if (not isinstance(state, dict) or any(not isinstance(k, str) or not k
                or not _finite(v) for k, v in state.items())):
            raise ValueError("math state requires named finite scalar fields")
        return {key: float(value) for key, value in state.items()}

    @staticmethod
    def _display(number, state):
        source = number["source"]
        if source not in state:
            raise ValueError(f"unknown derived number source: {source}")
        value = state[source]
        if not number["domain"][0] <= value <= number["domain"][1]:
            raise ValueError(f"derived number source outside domain: {source}")
        rounded = Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_EVEN)
        return format(rounded, ".2f")

    def derived_number(self, id: str, *, source: str, domain: tuple[float, float],
                       decimals: int = 2, role: str = "body",
                       position: tuple[float, float, float], parent: str | None = None) -> Text:
        if type(decimals) is not int or decimals != 2:
            raise ValueError("decimals must be 2")
        if not isinstance(source, str) or not source:
            raise ValueError("source must name a state field")
        if (not isinstance(domain, tuple) or len(domain) != 2
                or not all(_finite(v) for v in domain) or domain[0] > domain[1]):
            raise ValueError("domain must be a finite ordered pair")
        if role not in self.font_sizes:
            raise ValueError("unknown font role")
        if (not isinstance(position, tuple) or len(position) != 3
                or not all(_finite(v) for v in position)):
            raise ValueError("position must contain three finite coordinates")
        state = self._state()
        number = {"source": source, "domain": list(domain), "decimals": decimals,
                  "role": role, "position": position, "unrounded": state.get(source)}
        display = self._display(number, state)
        label = Text(display, font=FONT, font_size=self.font_sizes[role],
                     color=self.theme["colors"]["foreground"]).move_to(position)
        self.track(id, label, "text", role=role, parent=parent)
        number.update(mobject=label, display=display)
        self._snapshot_number(number)
        self._derived_numbers[id] = number
        return label

    @staticmethod
    def _snapshot_number(number):
        label = number["mobject"]
        number["glyphs"] = tuple(label._research_glyphs)
        number["points"] = tuple(g.points.copy() for g in number["glyphs"])

    def _number_intact(self, number):
        label = number["mobject"]
        glyphs = number["glyphs"]
        return bool(self._source_text(label) == number["display"] and label.font == FONT
                and label._research_glyphs == glyphs
                and all(g in label.submobjects and not g.submobjects
                        and np.array_equal(g.points, points)
                        for g, points in zip(glyphs, number["points"]))
                and abs(self._record_font_size(label) - self.font_sizes[number["role"]]) < .01)

    @staticmethod
    def _record_font_size(label):
        points = np.concatenate([g.points for g in label._research_glyphs])
        return float(label.font_size) * np.ptp(points[:, 1]) / label.height

    def _prepare_preview_frame(self):
        if self._preview_steps is None or self._frame_count >= self.slide_timing["frames"]:
            raise ValueError("preview frame emitted outside frozen preview beat")
        state = self._state()
        self._math_state = dict(state)
        # Hand the author a copy: mutation cannot alter the trace's canonical state.
        self.update_geometry(dict(state))
        for number in self._derived_numbers.values():
            display = self._display(number, state)
            # Never overwrite a transform, font/scale violation or nested child.
            # The normal observer will report its original geometry and errors.
            if not self._number_intact(number):
                continue
            number["unrounded"] = state[number["source"]]
            if display == number["display"]:
                continue
            label = number["mobject"]
            replacement = Text(display, font=FONT, font_size=self.font_sizes[number["role"]],
                color=self.theme["colors"]["foreground"]).move_to(number["position"])
            # Replace ONLY owned glyphs. Independent attached children survive
            # refresh and remain visible to the original registration audit.
            extras = [part for part in label.submobjects if part not in number["glyphs"]]
            label.submobjects = [*replacement.submobjects, *extras]
            for name in ("text", "original_text", "chars", "initial_height", "_font_size"):
                setattr(label, name, getattr(replacement, name))
            label._research_glyphs = tuple(replacement.chars.submobjects)
            number["display"] = display
            self._snapshot_number(number)

    def _record(self, mob, *, allow_copy=False):
        record = super()._record(mob, allow_copy=allow_copy)
        number = self._derived_numbers.get(record["id"])
        # Semantic ID alone (or an animation's deepcopy token) grants nothing.
        if number is not None and mob is number["mobject"]:
            record["derived_number"] = {key: number[key] for key in
                ("source", "unrounded", "display", "decimals", "domain")}
            record["derived_number"]["valid"] = self._number_intact(number)
            record["derived_number"]["glyph_geometry"] = [
                {"path_bbox": [float(v) for v in (*np.min(g.points[:, :2], axis=0),
                                                  *np.max(g.points[:, :2], axis=0))],
                 "point_count": len(g.points),
                 "path_sha256": hashlib.sha256(g.points.tobytes()).hexdigest()}
                for g in self._glyphs(mob) if g.has_points()]
        return record

    def _copy_findings(self, records, phase="frame"):
        findings = super()._copy_findings(records, phase)
        valid = {record["id"] for record in records if record.get("derived_number", {}).get("valid")}
        findings = [f for f in findings if not (f["code"] == "screen_text"
                    and len(f["object_ids"]) == 1 and f["object_ids"][0] in valid)]
        for record in records:
            if "derived_number" in record and not record["derived_number"]["valid"]:
                findings.append(self._finding("derived_number", [record["id"]],
                    "derived label differs from its controlled numeric glyphs", phase))
        return findings

    def _frame_evidence(self):
        return {"math_state": dict(self._math_state)}

    def get_time_progression(self, run_time, description, n_iterations=None,
                             override_skip_animations=False):
        if self._preview_steps is None:
            return super().get_time_progression(run_time, description, n_iterations,
                                               override_skip_animations)
        return tqdm((frame / self.fps for frame in range(self._preview_steps)),
                    total=self._preview_steps, desc=description,
                    disable=config.progress_bar == "none")

    def preview_beat(self, beat_id: str) -> None:
        beats = self.slide_timing["beats"]
        if self._beat_index >= len(beats) or beats[self._beat_index]["id"] != beat_id:
            raise ValueError("beat order differs from frozen timeline")
        timing = beats[self._beat_index]
        if self._frame_count != timing["local_start_frame"]:
            raise ValueError("frames emitted outside frozen beat boundaries")
        frames = timing["frames"]
        if type(frames) is not int or frames <= 0:
            raise ValueError("preview beat requires positive integer frames")
        before = self._frame_count
        self._preview_steps = frames
        try:
            self.play(Wait(run_time=frames / self.fps, frozen_frame=False))
        finally:
            self._preview_steps = None
        if self._frame_count != timing["local_end_frame"]:
            raise ValueError("rendered beat frame count differs from frozen timeline")
        self._beat_log.append({"id": beat_id, "animation_frames": self._frame_count-before,
                              "wait_frames": 0, "start_frame": before, "end_frame": self._frame_count})
        self._beat_index += 1

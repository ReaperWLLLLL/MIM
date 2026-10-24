"""A continuous original canvas: signed scores → positive terms → weights → y."""
from manim import Circle, Line, Rectangle

from research.preview_scene import SilentPreviewScene
from model import attention_state


class AttentionPreview(SilentPreviewScene):
    def state_at(self, local_frame: int) -> dict[str, float]:
        return attention_state(local_frame, self.fps)

    def update_geometry(self, state: dict[str, float]) -> None:
        for field, y in (("s1", .5), ("s2", -1.15)):
            self.dots[field].move_to([-4.85 + .7*state[field], y, 0])
        for field, y in (("e1", 1.1), ("e2", -.15)):
            width = .9 * state[field]
            self.bars[field].stretch_to_fit_width(width).move_to([-2.1+width/2, y, 0])
        width1, width2 = 3.2*state["a1"], 3.2*state["a2"]
        self.bars["a1"].stretch_to_fit_width(width1).move_to([-2.1+width1/2, -1.9, 0])
        self.bars["a2"].stretch_to_fit_width(width2).move_to([-2.1+width1+width2/2, -1.9, 0])
        for field in ("v1", "v2", "y"):
            self.dots[field].move_to([2.6+(state[field]-2)*3.5/8, -1.3, 0])

    def construct(self):
        self.dots, self.bars = {}, {}
        start, end = self.slide_timing["start_frame"], self.slide_timing["end_frame"]
        colors = self.theme["colors"]
        first, second, output = colors["primary"], colors["secondary"], colors["accent"]

        def label(key, x, y, role="body", color=None):
            kwargs = {} if color is None else {"color": color}
            item = self.text(key, role=role, **kwargs).move_to([x, y, 0])
            self.add(item)
            return item

        def number(field, x, y, domain):
            self.add(self.derived_number(f"number_{field}", source=field,
                domain=domain, position=(x, y, 0)))

        def axis(identifier, x1, x2, y):
            item = self.track(identifier, Line([x1, y, 0], [x2, y, 0],
                color=colors["foreground"], stroke_width=2), "shape")
            self.add(item)

        def point(field, color, axis_id):
            item = self.track(f"dot_{field}", Circle(radius=.08, color=color,
                fill_opacity=1, stroke_width=0), "shape")
            self.dots[field] = item
            self.add(item)
            self.math_contact(f"point_{field}", kind="point_on_number_line",
                objects=(f"dot_{field}", axis_id), start_frame=start, end_frame=end)

        def bar(field, color):
            item = self.track(f"bar_{field}", Rectangle(width=1, height=.23,
                color=color, fill_opacity=1, stroke_width=0), "shape")
            self.bars[field] = item
            self.add(item)

        label("query", -5.5, 2.35)
        number("q", -3.6, 2.35, (-1.1, 1.1))
        label("score", -4.85, 1.65)
        for field, label_key, zero_key, value_y, axis_y, color in (
            ("s1", "score1", "zero1", .95, .5, first),
            ("s2", "score2", "zero2", -.7, -1.15, second),
        ):
            label(label_key, -6.05, value_y, color=color)
            number(field, -3.3, value_y, (-1.1, 1.1))
            axis(f"axis_{field}", -5.8, -3.9, axis_y)
            point(field, color, f"axis_{field}")
            label(zero_key, -4.85, axis_y-.4, role="caption")

        label("exponent", -.5, 2.35)
        for field, key, y, color in (("e1", "exp1", 1.65, first),
                                   ("e2", "exp2", .4, second)):
            label(key, -2.05, y, color=color)
            number(field, .85, y, (.3, 3.01))
            bar(field, color)
        label("exp_scale", -.5, -.72, role="caption")
        label("weight", -.5, -1.32)
        bar("a1", first)
        bar("a2", second)
        self.math_contact("weight_join", kind="adjacent_weight_segments",
            objects=("bar_a1", "bar_a2"), start_frame=start, end_frame=end)
        for field, key, x, color in (("a1", "weight1", -1.4, first),
                                    ("a2", "weight2", .4, second)):
            label(key, x, -2.43, color=color)
            number(field, x, -2.95, (0, 1))
        label("total", -.5, -3.42, role="caption")

        label("value1", 3, 2.35, color=first)
        label("value2", 5.65, 2.35, color=second)
        number("v1", 3, 1.72, (2, 2))
        number("v2", 5.65, 1.72, (6, 10))
        label("result", 4.35, .65, color=output)
        number("y", 4.35, 0, (2, 10))
        axis("value_axis", 2.6, 6.1, -1.3)
        for field, color in (("v1", first), ("v2", second), ("y", output)):
            point(field, color, "value_axis")
        label("axis2", 2.6, -1.88, role="caption")
        label("axis10", 6.1, -1.88, role="caption")
        self.update_geometry(self.state_at(0))

        # Only the short stage sentence changes; all mathematical objects persist.
        phase = None
        for beat, text in (("establish", "equal"), ("match_second", "prefer_second"),
                           ("reverse", "prefer_first"), ("restore", "restore"),
                           ("value_only", "change_value"), ("summarize", None)):
            if phase is not None:
                self.remove(phase)
            phase = label(text, 0, 3.2) if text is not None else None
            if beat == "summarize":
                label("formula", -4.7, -2.65)
                label("calculation", 4.35, -2.65)
            self.preview_beat(beat)

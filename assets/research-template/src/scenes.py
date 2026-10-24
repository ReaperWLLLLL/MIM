"""Small generic example; timing comes exclusively from verified voice WAVs."""
from manim import Arrow, FadeIn, Rectangle, RIGHT
from research.scene import ResearchScene


class Example(ResearchScene):
    def construct(self):
        colors = self.theme["colors"]
        title = self.text("title", role="title").move_to([0, 2.7, 0])
        left = self.track("input-box", Rectangle(width=2.8, height=1.8,
            color=colors["primary"], stroke_width=self.theme["line_width"]).move_to([-3, .2, 0]), "container")
        right = self.track("output-box", Rectangle(width=2.8, height=1.8,
            color=colors["secondary"], stroke_width=self.theme["line_width"]).move_to([3, .2, 0]), "container")
        input_label = self.text("input", parent="input-box").move_to(left)
        output_label = self.text("output", parent="output-box").move_to(right)
        link = self.track("measurement", Arrow(left.get_right(), right.get_left(), buff=0,
            color=colors["accent"], stroke_width=self.theme["line_width"], tip_length=.2),
            "connector", endpoints=("input-box", "output-box"))
        caption = self.text("caption", role="caption").move_to([-.4, -2.2, 0])
        self.add(title, caption)
        self.beat("observe", [FadeIn(m) for m in (left, right, input_label, output_label, link)], .2)
        self.beat("compare", [caption.animate.shift(.8 * RIGHT)], .2)

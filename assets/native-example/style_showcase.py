"""Original branch-to-matrix animation in three art directions.

Render any of Midnight, Daylight, Notebook. See references/visual-styles.md.
The two currents enter the branch at their respective nodes; this is a local
branch stamp, not an assertion that the complete network matrix is singular.
"""
import os
import sys
from pathlib import Path

import manimpango
from manim import (
    DOWN, LEFT, RIGHT, UP, Arrow, Create, CurvedArrow, Dot, FadeIn,
    Indicate, Line, MathTex, Matrix, Scene, Text, TransformFromCopy, VGroup,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from styles import load_style


class BranchStyle(Scene):
    style_name = "midnight"

    def construct(self):
        s = load_style(self.style_name)
        self.camera.background_color = s["background"]
        font_file = os.environ.get("MANIM_CHINESE_FONT_FILE")
        if font_file:
            if not Path(font_file).is_file():
                raise FileNotFoundError(font_file)
            manimpango.register_font(font_file)
        font = os.environ.get("MANIM_CHINESE_FONT", "Microsoft YaHei")
        if font not in manimpango.list_fonts():
            raise ValueError(f"Install a licensed {font} font or set MANIM_CHINESE_FONT")

        def prose(value, size=s["body_size"], color=None):
            return Text(value, font=font, font_size=size, color=color or s["foreground"])

        def math(value, color=None):
            return MathTex(value, font_size=s["math_size"], color=color or s["foreground"])

        title = prose("一条支路，怎样写进矩阵", s["title_size"])
        tag = prose(s["label"], 19, s["muted"])
        title.move_to([0, 3.05, 0])
        tag.to_corner(UP + RIGHT, buff=.36)
        if s["layout"] == "notebook":
            for y in (-2.8, -2, -1.2, -.4, .4, 1.2, 2):
                self.add(Line([-6.5, y, 0], [6.5, y, 0], color=s["rule"], stroke_width=.8))
            self.add(Line([-5.85, -3.4, 0], [-5.85, 2.4, 0], color=s["accent"], stroke_width=1, stroke_opacity=.25))
        elif s["layout"] == "columns":
            title.to_edge(LEFT, buff=.7)
            self.add(Line([-.1, -2.7, 0], [-.1, 2.1, 0], color=s["rule"], stroke_width=1.2))
        if s["layout"] != "centered":
            self.add(Line(title.get_left() + DOWN*.48, title.get_right() + DOWN*.48,
                          color=s["accent"], stroke_width=s["line_width"]))

        centered = s["layout"] == "centered"
        a, b = ([-2, 1.7, 0], [2, 1.7, 0]) if centered else ([-4.9, 1, 0], [-1.2, 1, 0])
        dots = VGroup(Dot(a, color=s["primary"]), Dot(b, color=s["secondary"]))
        branch = Line(a, b, color=s["accent"], stroke_width=s["line_width"])
        labels = VGroup(math("i", s["primary"]).next_to(dots[0], DOWN, buff=.18),
                        math("j", s["secondary"]).next_to(dots[1], DOWN, buff=.18))
        y_label = math("y", s["accent"]).next_to(branch, UP, buff=.12)
        currents = VGroup(
            math(r"I_i=y(V_i-V_j)", s["primary"]),
            math(r"I_j=y(V_j-V_i)", s["secondary"]),
        )
        if centered:
            currents.arrange(RIGHT, buff=.9).move_to([0, .1, 0])
        else:
            currents.arrange(DOWN, buff=.3, aligned_edge=LEFT).move_to([3, 1.15, 0])
        arrows = VGroup(
            Arrow(dots[0].get_center()+UP*.65, dots[0].get_center()+UP*.65+RIGHT*.75,
                  buff=0, color=s["primary"], stroke_width=2.5),
            Arrow(dots[1].get_center()+UP*.65, dots[1].get_center()+UP*.65+LEFT*.75,
                  buff=0, color=s["secondary"], stroke_width=2.5),
        )
        matrix = Matrix([["y", "-y"], ["-y", "y"]], element_to_mobject=math,
                        h_buff=1.1, v_buff=.7, bracket_h_buff=.2)
        matrix.set_color(s["foreground"])
        matrix.get_rows()[0].set_color(s["primary"])
        matrix.get_rows()[1].set_color(s["secondary"])
        matrix.move_to([0 if centered else 3, -1.5, 0])
        stamp = math(r"\Delta Y=").next_to(matrix, LEFT, buff=.25)
        caption = prose("两端电压的系数，填入对应行列", 25)
        caption.move_to([0, -3.1, 0])
        self.play(FadeIn(title, tag), run_time=.6)
        self.play(Create(branch), FadeIn(dots, labels, y_label), run_time=.8)
        self.play(*[Create(a) for a in arrows], run_time=.6)
        self.play(FadeIn(currents[0]), run_time=.7)
        self.wait(.5)
        self.play(FadeIn(currents[1]), run_time=.7)
        self.wait(.5)
        self.play(FadeIn(matrix.get_brackets(), stamp), run_time=.5)
        for equation, row in zip(currents, matrix.get_rows()):
            self.play(TransformFromCopy(equation, row), run_time=1)
        if s["layout"] == "notebook":
            pointer = CurvedArrow([-2.7, -.1, 0], [.8, -1.4, 0], angle=.5,
                                  color=s["accent"], stroke_width=2)
            self.play(Create(pointer), run_time=.6)
        self.play(FadeIn(caption), run_time=.6)
        self.play(Indicate(matrix.get_entries()[0], color=s["accent"]),
                  Indicate(matrix.get_entries()[3], color=s["accent"]), run_time=.8)
        self.wait(2)


class Midnight(BranchStyle):
    style_name = "midnight"


class Daylight(BranchStyle):
    style_name = "daylight"


class Notebook(BranchStyle):
    style_name = "notebook"

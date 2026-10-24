"""Chinese prose and actual inline mathematics, with no private font bundled.

Set MANIM_CHINESE_FONT_FILE to a legally installed font if font discovery misses it.
Render: python -m manim -ql mixed_math.py MixedMathCaption
"""
import os
from pathlib import Path

import manimpango
from manim import DOWN, RIGHT, UP, FadeIn, MathTex, Scene, Text, VGroup


class MixedMathCaption(Scene):
    def construct(self):
        self.camera.background_color = '#0B1120'
        font_file = os.environ.get('MANIM_CHINESE_FONT_FILE')
        if font_file and Path(font_file).is_file():
            manimpango.register_font(font_file)
        prose = dict(font='Microsoft YaHei', font_size=27, color='#EDF4F6')
        title = Text('正文里的数学，也按数学排版', **prose).to_edge(UP, buff=.9)
        rows = VGroup(
            VGroup(
                Text('树支列组成', **prose), MathTex(r'A_T', font_size=32, color='#66E0C2'),
                Text('，连支列组成', **prose), MathTex(r'A_L', font_size=32, color='#B7A6FF'),
            ).arrange(RIGHT, buff=.08),
            VGroup(
                Text('矩阵', **prose), MathTex('A', font_size=32),
                Text('的转置记为', **prose), MathTex(r'A^T', font_size=32),
            ).arrange(RIGHT, buff=.08),
            VGroup(
                Text('若', **prose), MathTex('Y', font_size=32),
                Text('可逆，则', **prose), MathTex(r'V=Y^{-1}I', font_size=32),
            ).arrange(RIGHT, buff=.08),
        ).arrange(DOWN, buff=.75)
        self.play(FadeIn(title))
        for row in rows:
            self.play(FadeIn(row), run_time=.5)
            self.wait(.8)
        self.wait(2)

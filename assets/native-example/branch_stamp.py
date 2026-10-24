"""Original example; render with manim -ql branch_stamp.py BranchStamp."""
from manim import Scene, Dot, Line, MathTex, Matrix, VGroup, Create, FadeIn, TransformFromCopy, Indicate, UP, DOWN

class BranchStamp(Scene):
    def construct(self):
        self.camera.background_color = '#0B1120'
        left, right = Dot([-3,1,0]), Dot([3,1,0])
        branch=Line(left.get_center(),right.get_center(),color='#66E0C2')
        labels=VGroup(MathTex('i').next_to(left,UP), MathTex('j').next_to(right,UP))
        y=MathTex('y').next_to(branch,UP)
        currents=VGroup(MathTex('I_i=y(V_i-V_j)'),MathTex('I_j=y(V_j-V_i)')).arrange(DOWN).shift(DOWN)
        self.play(Create(branch),FadeIn(left,right,labels,y))
        self.play(FadeIn(currents)); self.wait(2)
        self.play(currents.animate.scale(.8).shift(UP*.2))
        matrix=Matrix([['y','-y'],['-y','y']]).shift(DOWN*2.5)
        self.play(FadeIn(matrix.get_brackets()))
        self.play(*[TransformFromCopy(y,e) for e in matrix.get_entries()])
        self.play(Indicate(matrix.get_rows()[0],color='#66E0C2'))
        self.wait(3)

from manim import *
from vnotes import NotesScene

LAYOUT = {
    "s": (1, 0),
    "a": (0, 1),
    "b": (2, 1),
    "e": (2, 0),
    "c": (0, 2),
    "d": (2, 2),
    "g": (1, 3),
}
EDGES = [
    ("s", "a"),
    ("s", "b"),
    ("s", "e"),
    ("a", "c"),
    ("b", "c"),
    ("b", "d"),
    ("c", "g"),
    ("d", "g"),
]


def place(row, column, left, top, dx, dy):
    return np.array([left + column * dx, top - row * dy, 0])


class C01(NotesScene):
    def graph(self, left, top, dx, dy, radius, size):
        nodes = {}
        for key, (row, column) in LAYOUT.items():
            circle = Circle(radius=radius, color=self.color("line"), stroke_width=3)
            circle.set_fill(self.color("background"), opacity=1).move_to(
                place(row, column, left, top, dx, dy)
            )
            nodes[key] = circle
        names = {
            "s": self.label("ns", size=size),
            "a": self.label("na", size=size),
            "b": self.label("nb", size=size),
            "c": self.label("nc", size=size),
            "d": self.label("nd", size=size),
            "e": self.label("ne", size=size),
            "g": self.label("ng", size=size),
        }
        for key, name in names.items():
            name.move_to(nodes[key])
        edges = VGroup(
            *[
                Line(
                    nodes[u].get_center(),
                    nodes[v].get_center(),
                    buff=radius,
                    color=self.color("line"),
                    stroke_width=3,
                )
                for u, v in EDGES
            ]
        )
        return nodes, names, edges

    def construct(self):
        with self.beat("b01") as b:
            nodes, names, edges = self.graph(-6.2, 1.9, 2.3, 1.9, 0.42, 32)
            with self.cue(1) as cue:
                self.play(
                    Create(edges),
                    *[FadeIn(node) for node in nodes.values()],
                    run_time=cue.share(0.55),
                )
                self.play(*[FadeIn(name) for name in names.values()], run_time=cue.share(0.3))
            with self.cue(2) as cue:
                settle = self.label("settle", size=32, width=4.2).move_to(np.array([4.6, 1.0, 0]))
                relax = (
                    self.label("relax", size=32, width=4.2)
                    .next_to(settle, DOWN, buff=0.6)
                    .align_to(settle, LEFT)
                )
                self.play(
                    nodes["s"]
                    .animate.set_fill(self.color("visited"), opacity=1)
                    .set_stroke(self.color("accent")),
                    FadeIn(settle, shift=RIGHT * 0.2),
                    run_time=cue.share(0.4),
                )
                fan = VGroup(*[edges[i] for i in range(3)])
                self.play(
                    fan.animate.set_color(self.color("accent")),
                    FadeIn(relax, shift=RIGHT * 0.2),
                    run_time=cue.share(0.4),
                )


class C02(NotesScene):
    def construct(self):
        with self.beat("b02") as b:
            left, right = np.array([-3.2, -0.6, 0]), np.array([3.2, -0.6, 0])
            c = (
                Circle(radius=0.75, color=self.color("accent"), stroke_width=4)
                .set_fill(self.color("visited"), opacity=1)
                .move_to(left)
            )
            v = (
                Circle(radius=0.75, color=self.color("line"), stroke_width=4)
                .set_fill(self.color("background"), opacity=1)
                .move_to(right)
            )
            c_name = self.label("c", size=44).move_to(c)
            v_name = self.label("b", size=44).move_to(v)
            edge = Arrow(left, right, buff=0.8, color=self.color("line"), stroke_width=5)
            dc = self.number("dc", size=44).next_to(c, UP, buff=0.35)
            db = self.number("db", size=44).next_to(v, UP, buff=0.35)
            with self.cue(1) as cue:
                self.play(
                    FadeIn(c),
                    FadeIn(v),
                    Create(edge),
                    FadeIn(c_name),
                    FadeIn(v_name),
                    run_time=cue.share(0.5),
                )
                self.play(
                    FadeIn(dc, shift=UP * 0.2), FadeIn(db, shift=UP * 0.2), run_time=cue.share(0.4)
                )
            with self.cue(2) as cue:
                weight = self.number("w", size=40).next_to(edge, DOWN, buff=0.25)
                rule = self.math("rule", size=40).move_to(np.array([0, 2.6, 0]))
                self.play(
                    FadeIn(weight, shift=UP * 0.15),
                    edge.animate.set_color(self.color("accent")),
                    run_time=cue.share(0.35),
                )
                self.play(Write(rule), run_time=cue.share(0.5))
            with self.cue(3) as cue:
                lowered = self.number("dnew", size=44, color="positive").move_to(db)
                self.play(
                    Transform(db, lowered),
                    v.animate.set_stroke(self.color("positive")),
                    run_time=cue.share(0.45),
                )
                self.play(
                    Indicate(db, color=self.color("positive"), scale_factor=1.15),
                    run_time=cue.share(0.4),
                )


class C03(NotesScene):
    def construct(self):
        with self.beat("b03") as b:
            nodes, names, edges = C01.graph(self, -4.2, 3.2, 2.8, 1.15, 0.42, 32)
            order = ["s", "e", "a", "c", "b", "d", "g"]
            table = self.grid(
                [
                    ["hs", "he", "ha", "hc", "hb", "hd", "hg"],
                    ["ds", "de", "da", "dc4", "db5", "dd", "dg"],
                ],
                header=True, size=44).move_to(np.array([0, -1.75, 0]))
            values = [table.cell(1, column) for column in range(7)]
            for value in values:
                value.set_opacity(0)

            def settle(key, column):
                return [
                    nodes[key]
                    .animate.set_fill(self.color("visited"), opacity=1)
                    .set_stroke(self.color("accent")),
                    values[column].animate.set_opacity(1),
                ]

            with self.cue(1) as cue:
                self.play(
                    Create(edges),
                    *[FadeIn(node) for node in nodes.values()],
                    *[FadeIn(name) for name in names.values()],
                    FadeIn(table),
                    run_time=cue.share(0.6),
                )
                self.play(*settle("s", 0), run_time=cue.share(0.3))
            with self.cue(2) as cue:
                self.play(*settle("e", 1), run_time=cue.share(0.4))
                self.play(*settle("a", 2), run_time=cue.share(0.4))
            with self.cue(3) as cue:
                self.play(*settle("c", 3), run_time=cue.share(0.35))
                self.play(
                    *settle("b", 4),
                    edges[4].animate.set_color(self.color("positive")),
                    run_time=cue.share(0.4),
                )
            with self.cue(4) as cue:
                self.play(*settle("d", 5), run_time=cue.share(0.3))
                self.play(
                    *settle("g", 6),
                    edges[7].animate.set_color(self.color("positive")),
                    FadeIn(table.highlight(1)),
                    run_time=cue.share(0.45),
                )


class C04(NotesScene):
    def construct(self):
        with self.beat("b04") as b:
            s_at, x_at, y_at = (
                np.array([-4.2, -0.4, 0]),
                np.array([0.4, 1.6, 0]),
                np.array([0.4, -2.2, 0]),
            )
            spots = {"s": s_at, "x": x_at, "y": y_at}
            circles = {
                key: Circle(radius=0.6, color=self.color("line"), stroke_width=4)
                .set_fill(self.color("background"), opacity=1)
                .move_to(at)
                for key, at in spots.items()
            }
            labels = {
                "s": self.label("s", size=40),
                "x": self.label("x", size=40),
                "y": self.label("y", size=40),
            }
            for key, label in labels.items():
                label.move_to(circles[key])
            sx = Arrow(s_at, x_at, buff=0.65, color=self.color("line"), stroke_width=5)
            sy = Arrow(s_at, y_at, buff=0.65, color=self.color("line"), stroke_width=5)
            yx = Arrow(y_at, x_at, buff=0.65, color=self.color("negative"), stroke_width=5)
            wx = self.number("wx", size=36).next_to(sx.get_center(), UP + LEFT * 0.4, buff=0.2)
            wy = self.number("wy", size=36).next_to(sy.get_center(), DOWN + LEFT * 0.4, buff=0.2)
            wneg = self.number("wneg", size=36, color="negative").next_to(
                yx, RIGHT, buff=0.25
            )
            with self.cue(1) as cue:
                self.play(
                    *[FadeIn(circle) for circle in circles.values()],
                    *[FadeIn(label) for label in labels.values()],
                    Create(sx),
                    Create(sy),
                    Create(yx),
                    FadeIn(wx),
                    FadeIn(wy),
                    FadeIn(wneg),
                    run_time=cue.share(0.7),
                )
            with self.cue(2) as cue:
                wrong = self.label("wrong", size=32).next_to(circles["x"], RIGHT, buff=0.45)
                self.play(
                    circles["x"]
                    .animate.set_fill(self.color("visited"), opacity=1)
                    .set_stroke(self.color("accent")),
                    FadeIn(wrong, shift=LEFT * 0.2),
                    run_time=cue.share(0.6),
                )
            with self.cue(3) as cue:
                true = (
                    self.label("true", size=32, color="positive")
                    .next_to(wrong, DOWN, buff=0.35)
                    .align_to(wrong, LEFT)
                )
                self.play(
                    sy.animate.set_color(self.color("positive")),
                    yx.animate.set_color(self.color("positive")),
                    run_time=cue.share(0.4),
                )
                self.play(FadeIn(true, shift=LEFT * 0.2), run_time=cue.share(0.3))
            with self.cue(4) as cue:
                self.play(
                    wrong.animate.set_color(self.color("negative")),
                    Indicate(circles["x"], color=self.color("negative")),
                    run_time=cue.share(0.6),
                )
        with self.beat("b05") as b:
            keep = VGroup(
                *circles.values(), *labels.values(), sx, sy, yx, wx, wy, wneg, wrong, true
            )
            recap = VGroup(
                self.label("r1", size=44), self.label("r2", size=44), self.label("r3", size=44)
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.45)
            recap.move_to(np.array([0, 0.3, 0]))
            with self.cue(1) as cue:
                self.play(FadeOut(keep), run_time=cue.share(0.25))
                for line in recap:
                    self.play(FadeIn(line, shift=UP * 0.15), run_time=cue.share(0.18))

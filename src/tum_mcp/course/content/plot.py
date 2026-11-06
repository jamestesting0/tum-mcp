"""Build-time sampling of plot functions: a small safe expression language, sampled adaptively.

A function series such as ``1/(1+exp(-x))`` is evaluated here, never in the browser. The sampler
refines where the curve bends, breaks the line where the function is undefined, jumps or runs to
a pole, and clips it to the plot window instead of drawing flat plateaus at the edges.
"""

import ast
import math
from collections.abc import Callable

FUNCTIONS: dict[str, Callable[..., float]] = {
    "exp": math.exp,
    "log": math.log,
    "ln": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}
CONSTANTS = {"pi": math.pi, "e": math.e}
OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}
Point = tuple[float, float]


def compile_expression(text: str) -> Callable[[float], float | None]:
    """Accept arithmetic in x with the functions above; reject anything else."""
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval").body
    except SyntaxError:
        raise ValueError(f"A plot function is not a valid expression: {text}") from None

    def check(node: ast.expr) -> None:
        match node:
            case ast.Constant(value=int() | float()) if not isinstance(node.value, bool):
                return
            case ast.Name(id=name) if name == "x" or name in CONSTANTS:
                return
            case ast.BinOp(op=op) if type(op) in OPERATORS:
                check(node.left)
                check(node.right)
                return
            case ast.UnaryOp(op=ast.USub() | ast.UAdd()):
                check(node.operand)
                return
            case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if (
                name in FUNCTIONS and args
            ):
                for argument in args:
                    check(argument)
                return
        raise ValueError(
            f"A plot function may use only x, numbers, + - * / ^ and {', '.join(FUNCTIONS)}."
        )

    check(tree)

    def run(node: ast.expr, x: float) -> float:
        match node:
            case ast.Constant(value=value):
                return float(value)  # floats overflow instead of growing without bound
            case ast.Name(id="x"):
                return x
            case ast.Name(id=name):
                return CONSTANTS[name]
            case ast.BinOp(op=op, left=left, right=right):
                return OPERATORS[type(op)](run(left, x), run(right, x))
            case ast.UnaryOp(op=ast.USub(), operand=operand):
                return -run(operand, x)
            case ast.UnaryOp(operand=operand):
                return run(operand, x)
            case ast.Call(func=ast.Name(id=name), args=args):
                return float(FUNCTIONS[name](*(run(argument, x) for argument in args)))
        raise ValueError("Unsupported plot expression.")

    def value(x: float) -> float | None:
        try:
            y = run(tree, x)
        except (ValueError, ZeroDivisionError, OverflowError, TypeError):
            return None
        return (
            y if isinstance(y, float) and math.isfinite(y) and not isinstance(y, complex) else None
        )

    return value


def sample(
    text: str,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    *,
    log_y: bool = False,
    tolerance: float = 0.35,
) -> list[list[Point]]:
    """Pieces of the curve inside the window, refined to `tolerance` pixels on a 600x360 plot."""
    f = compile_expression(text)
    x0, x1 = x_range
    y0, y1 = (math.log10(y_range[0]), math.log10(y_range[1])) if log_y else y_range

    def g(x: float) -> float | None:
        y = f(x)
        if y is None or not log_y:
            return y
        return math.log10(y) if y > 0 else None

    sx, sy, span = 600 / (x1 - x0), 360 / (y1 - y0), y1 - y0
    base = [x0 + (x1 - x0) * i / 64 for i in range(65)]
    coarse = [(x, g(x)) for x in base]

    def refine(
        a: float, fa: float | None, b: float, fb: float | None, depth: int
    ) -> list[tuple[float, float | None]]:
        if depth > 14 or fa is None or fb is None:
            if depth <= 14 and (fa is None) != (fb is None):
                middle = (a + b) / 2
                fm = g(middle)
                return refine(a, fa, middle, fm, depth + 1) + refine(middle, fm, b, fb, depth + 1)
            return [(b, fb)]
        middle = (a + b) / 2
        fm = g(middle)
        if fm is None or abs(fm - (fa + fb) / 2) * sy > tolerance or abs(fb - fa) > span / 4:
            return refine(a, fa, middle, fm, depth + 1) + refine(middle, fm, b, fb, depth + 1)
        return [(b, fb)]

    dense: list[tuple[float, float | None]] = [coarse[0]]
    for (a, fa), (b, fb) in zip(coarse, coarse[1:], strict=False):
        dense += refine(a, fa, b, fb, 0)
    pieces: list[list[Point]] = []
    current: list[Point] = []
    for x, y in dense:
        if y is None:
            if current:
                pieces.append(current)
            current = []
            continue
        # A jump of several pixels between samples a hair apart is a pole or a step: break there.
        if current and abs(y - current[-1][1]) * sy > 3 and (x - current[-1][0]) * sx < 0.2:
            pieces.append(current)
            current = []
        current.append((x, y))
    if current:
        pieces.append(current)
    clipped: list[list[Point]] = []
    for piece in pieces:
        run: list[Point] = []
        for x, y in piece:
            if y0 - span * 0.02 <= y <= y1 + span * 0.02:
                run.append((round(x, 6), round(10**y if log_y else y, 6)))
            else:
                if len(run) > 1:
                    clipped.append(run)
                run = []
        if len(run) > 1:
            clipped.append(run)
    if not clipped:
        raise ValueError(f"The plot function {text} has no visible piece inside the window.")
    return clipped

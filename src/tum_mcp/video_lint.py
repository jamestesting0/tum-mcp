"""Static checks for agent-written chapter scenes. A guard against mistakes, not a sandbox."""

import ast
from dataclasses import dataclass

from tum_mcp.video_content import Storyboard

ALLOWED_IMPORTS = {"manim", "numpy", "math", "vnotes"}
FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "input",
    "breakpoint",
    "exit",
    "quit",
    "os",
    "sys",
    "subprocess",
    "socket",
    "pathlib",
    "Path",
    "shutil",
    "importlib",
    "ctypes",
    "builtins",
    "__builtins__",
    "config",
    "tempconfig",
}
TEXT_CONSTRUCTORS = {
    "Text",
    "MarkupText",
    "Paragraph",
    "Tex",
    "MathTex",
    "SingleStringMathTex",
    "Typst",
    "MathTypst",
    "Code",
    "DecimalNumber",
    "Integer",
    "Variable",
    "Title",
    "BulletedList",
    "MathTable",
    "Table",
    "DecimalTable",
    "IntegerTable",
    "MobjectTable",
    "BraceLabel",
    "BraceText",
    "LabeledDot",
    "LabeledLine",
    "LabeledArrow",
    "ImageMobject",
    "SVGMobject",
}
KNOWN_BAD = {
    "ShowCreation": "ManimGL name; use Create",
    "TexMobject": "removed API; use self.math(...)",
    "TextMobject": "removed API; use self.label(...)",
    "ShowCreationThenDestruction": "ManimGL name; use ShowPassingFlash",
    "manimlib": "ManimGL import; this runtime is Manim Community",
    "CONFIG": "ManimGL class configuration is not supported",
    "embed": "interactive embedding is not available while rendering",
    "add_sound": "narration is mixed by the pipeline from measured audio",
    "add_subcaption": "captions are generated from timing.json",
}
FILE_ATTRIBUTES = {
    "load",
    "save",
    "savez",
    "savez_compressed",
    "savetxt",
    "loadtxt",
    "genfromtxt",
    "fromfile",
    "tofile",
    "memmap",
    "DataSource",
    "lib",
    "ctypeslib",
    "renderer",
    "manager",
}
HELPERS = {"label": "label", "math": "math", "number": "number", "value": "number", "code": "code"}


@dataclass(frozen=True)
class LintReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def lint(source: str, storyboard: Storyboard) -> LintReport:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(source, filename="chapters.py")
    except SyntaxError as error:
        return LintReport((f"syntax line {error.lineno}: {error.msg}",), ())
    screen = storyboard.screen()
    used: set[str] = set()
    beats_by_chapter = {c.key: [b.key for b in c.beats] for c in storyboard.chapters}
    classes: dict[str, list[str]] = {}

    def where(node: ast.AST) -> str:
        return f"line {getattr(node, 'lineno', '?')}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    errors.append(f"import {where(node)}: {alias.name} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORTS:
                errors.append(f"import {where(node)}: from {node.module} is not allowed")
            for alias in node.names:
                # An alias would hide a blocked name from the checks on later uses.
                if {alias.name, alias.asname} & (FORBIDDEN_NAMES | TEXT_CONSTRUCTORS):
                    errors.append(f"import {where(node)}: {alias.name} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                errors.append(f"forbidden {where(node)}: {node.id}")
            if node.id in TEXT_CONSTRUCTORS:
                errors.append(
                    f"text {where(node)}: {node.id} is not allowed; use self.label/math/"
                    "number/code with storyboard keys"
                )
            if node.id in KNOWN_BAD:
                errors.append(f"api {where(node)}: {node.id}: {KNOWN_BAD[node.id]}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                errors.append(f"forbidden {where(node)}: dunder attribute {node.attr}")
            if node.attr in KNOWN_BAD:
                errors.append(f"api {where(node)}: {node.attr}: {KNOWN_BAD[node.attr]}")
            if node.attr in TEXT_CONSTRUCTORS:
                errors.append(f"text {where(node)}: {node.attr} is not allowed")
            if node.attr in FILE_ATTRIBUTES:
                errors.append(f"forbidden {where(node)}: .{node.attr} can touch files")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            owner = node.func.value
            is_self = isinstance(owner, ast.Name) and owner.id == "self"
            if is_self and name in HELPERS:
                key = _literal(node.args[0]) if node.args else None
                if key is None:
                    errors.append(f"key {where(node)}: self.{name}() needs a literal key")
                elif key not in screen:
                    errors.append(f"key {where(node)}: no on-screen item '{key}'")
                elif screen[key].kind != HELPERS[name]:
                    errors.append(
                        f"key {where(node)}: '{key}' is a {screen[key].kind}, not {HELPERS[name]}"
                    )
                else:
                    used.add(key)
            if (
                is_self
                and name in {"color", "beat"}
                and (not node.args or _literal(node.args[0]) is None)
            ):
                errors.append(f"key {where(node)}: self.{name}() needs a literal argument")
            if name == "set_value" and not (
                node.args
                and isinstance(node.args[0], ast.Call)
                and isinstance(node.args[0].func, ast.Attribute)
                and node.args[0].func.attr == "value"
            ):
                errors.append(f"value {where(node)}: set_value() targets must be self.value('key')")
        elif isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id in {"config", "manim"}:
                        errors.append(f"config {where(node)}: render settings are fixed")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            beats = [
                _literal(call.args[0])
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "beat"
                and call.args
            ]
            classes[node.name] = [beat for beat in beats if beat]
            bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
            if "NotesScene" not in bases:
                errors.append(f"class {node.name}: chapter scenes extend NotesScene")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        elif not isinstance(node, ast.Import | ast.ImportFrom | ast.Assign | ast.Expr):
            errors.append(f"module line {node.lineno}: only imports, constants and classes")
    for chapter, beats in beats_by_chapter.items():
        name = chapter.upper()
        if name not in classes:
            errors.append(f"chapter {chapter}: class {name}(NotesScene) is missing")
        elif classes[name] != beats:
            errors.append(
                f"chapter {chapter}: beats appear as {classes[name]}, storyboard has {beats}"
            )
    extra = sorted(set(classes) - {key.upper() for key in beats_by_chapter})
    if extra:
        errors.append("classes without a storyboard chapter: " + ", ".join(extra))
    unused = sorted(set(screen) - used)
    if unused:
        warnings.append("on-screen items never shown: " + ", ".join(unused))
    return LintReport(tuple(dict.fromkeys(errors)), tuple(warnings))

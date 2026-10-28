"""Where the game's code uses which sound, found by reading src/ rather than by running it.

The game loads every file in assets/sound/ under its name without the
extension (Game._load_sounds), and code reaches them by that name in three
ways, all of which are looked for in the string literals of every module:

- the name itself: play_sound("stamp"), ['Map_foot_steps_1', ...];
- an f-string that builds it: f"knock_{knock_num}" - a pattern, the
  formatted parts standing for anything;
- a literal ending in '_' that names a family: startswith('sheep_'),
  prefix = "chop_" - every sound starting with it, in any case.

Each use is remembered with the function it sits in, which is the best
short answer to "what is this sound for". A name played directly -
play_sound(...), sounds[...], sounds.get(...) - that no file answers to is
reported as missing.
"""

import ast
import re
from collections import namedtuple
from pathlib import Path

# One place in the code naming a sound, or a family or pattern of them
Reference = namedtuple('Reference', 'path line where code text regex how direct')

NAME, PATTERN, PREFIX = 'name', 'pattern', 'prefix'
MIN_LITERAL = 3          # shorter literals ('_', 'x') name nothing


def _plays(node):
    """The sound name argument if `node` plays or fetches a sound by name, else None."""
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', '')
        if name == 'play_sound':
            return node.args[0]
        if (name == 'get' and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute)
                and func.value.attr == 'sounds'):
            return node.args[0]
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == 'sounds':
        return node.slice
    return None


class _Scanner(ast.NodeVisitor):
    def __init__(self, path, lines):
        self.path = path
        self.lines = lines
        self.scope = []          # names of the classes and functions we are in
        self.direct = set()      # ids of the string nodes played directly
        self.found = []

    def _enter(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = visit_FunctionDef = visit_AsyncFunctionDef = _enter

    def generic_visit(self, node):
        arg = _plays(node)
        if arg is not None:
            self.direct.add(id(arg))
        super().generic_visit(node)

    def _add(self, node, text, regex, how):
        line = node.lineno
        code = self.lines[line - 1].strip() if line <= len(self.lines) else ''
        where = '.'.join(self.scope) or '(module)'
        self.found.append(Reference(self.path, line, where, code, text, regex, how, id(node) in self.direct))

    def visit_Constant(self, node):
        text = node.value
        if not isinstance(text, str) or len(text) < MIN_LITERAL or not re.fullmatch(r'[\w.-]+', text):
            return
        self._add(node, text, re.compile(re.escape(text)), NAME)
        if text.endswith('_'):
            self._add(node, text + '*', re.compile(re.escape(text) + '.+', re.IGNORECASE), PREFIX)

    def visit_JoinedStr(self, node):
        parts, shown = [], []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(re.escape(str(value.value)))
                shown.append(str(value.value))
            else:
                parts.append('.+')
                shown.append('{...}')
        text = ''.join(shown)
        # Only names: no spaces (messages), and something fixed to go by at the start
        if ' ' in text or not isinstance(node.values[0], ast.Constant) or len(shown[0]) < MIN_LITERAL - 1:
            return
        self._add(node, text, re.compile(''.join(parts)), PATTERN)
        # The parts inside are not names of their own: do not visit them


def scan(source_dir):
    """Every Reference in the .py files under `source_dir`, paths relative to its parent."""
    source_dir = Path(source_dir)
    base = source_dir.parent
    found = []
    for path in sorted(source_dir.rglob('*.py')):
        try:
            text = path.read_text(encoding='utf-8')
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        scanner = _Scanner(path.relative_to(base).as_posix(), text.splitlines())
        scanner.visit(tree)
        found.extend(scanner.found)
    return found


def uses_of(references, keys):
    """({key: [Reference]}, [Reference to nothing]) for the sound keys given.

    A literal counts only where it matches a sound (most strings in the code
    are no sound's name); the missing are the references played directly that
    match none.
    """
    uses = {key: [] for key in keys}
    missing = []
    for ref in references:
        hits = [key for key in keys if ref.regex.fullmatch(key)]
        for key in hits:
            uses[key].append(ref)
        if not hits and ref.direct and ref.how != PREFIX:
            missing.append(ref)
    return uses, missing

"""The simulation core stays headless: no pygame, no UI, no drawing models, no global random."""
import ast
import os
import pathlib
import subprocess
import sys

import src.sim

SIM_DIR = pathlib.Path(src.sim.__file__).parent
REPO_ROOT = SIM_DIR.parent.parent

# Run in a fresh interpreter: this test process has long since imported pygame
_IMPORT_ALL = """
import importlib, pkgutil, sys
sys.modules["pygame"] = None          # any `import pygame` now raises ImportError
import src.sim
for module in pkgutil.walk_packages(src.sim.__path__, "src.sim."):
    importlib.import_module(module.name)
forbidden = sorted(name for name in sys.modules
                   if name.split(".")[:2] in (["src", "ui"], ["src", "handlers"], ["src", "models"])
                   or name == "src.game" or name == "src.game_state")
print("FORBIDDEN:" + ",".join(forbidden))
"""


def test_every_sim_module_imports_without_pygame_or_the_game():
    result = subprocess.run([sys.executable, "-c", _IMPORT_ALL], cwd=REPO_ROOT,
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("FORBIDDEN:"), result.stdout


def _module_level_random_calls(path: pathlib.Path):
    """Calls like random.random() / random.normalvariate() — the global generator."""
    allowed = {"Random", "SystemRandom"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "random" and node.attr not in allowed):
            yield f"{path.relative_to(REPO_ROOT)}:{node.lineno}: random.{node.attr}"
        if isinstance(node, ast.ImportFrom) and node.module == "random":
            names = {a.name for a in node.names} - allowed
            if names:
                yield f"{path.relative_to(REPO_ROOT)}:{node.lineno}: from random import {', '.join(sorted(names))}"


def test_the_sim_never_draws_from_the_global_random():
    found = [hit for path in SIM_DIR.rglob("*.py") for hit in _module_level_random_calls(path)]
    assert found == []

"""Test bootstrap.

Adds the extension source root to ``sys.path`` so the bpy-free ``core`` package
can be imported standalone (without triggering ``spectral_render/__init__.py``,
which imports ``bpy``). This lets the pure-math modules run in plain CPython.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "spectral_render"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

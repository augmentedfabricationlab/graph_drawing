#! python3
# r: compas
"""
graph_drawing (loader stub). Paste this into a Rhino 8 Script component set to
Python 3. The component code lives in rhino/component.py of the repository,
so edits there and in the package take effect on the next recompute, without
touching the component. Inputs and outputs: see README.rst.

The stub finds the rhino folder next to the .gh file (in it, or in ../rhino),
or through the environment variable GRAPH_DRAWING_RHINO. If graph_drawing is
not installed in Rhino's Python, it adds the repository's src folder to the path.
"""
import os
import sys

RHINO_DIR = os.environ.get("GRAPH_DRAWING_RHINO", "")
if not RHINO_DIR:
    _gh = ghenv.Component.OnPingDocument().FilePath  # noqa: F821
    _cands = []
    if _gh:
        _here = os.path.dirname(_gh)
        _cands += [_here, os.path.join(_here, "rhino"), os.path.join(_here, "..", "rhino")]
    for _c in _cands:
        if os.path.isfile(os.path.join(_c, "component.py")) and os.path.isfile(os.path.join(_c, "gh_params.py")):
            RHINO_DIR = os.path.abspath(_c)
            break
if not RHINO_DIR:
    raise RuntimeError("rhino folder of graph_drawing not found: save the .gh next to it or set GRAPH_DRAWING_RHINO")

try:
    import graph_drawing  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(RHINO_DIR, "..", "src")))

_src = os.path.join(RHINO_DIR, "component.py")
exec(compile(open(_src, encoding="utf-8").read(), _src, "exec"))

"""
Drawings in Rhino and Grasshopper (Rhino 8 only).

Importing this package registers the scene objects, so that
``compas.scene.Scene().add(drawing)`` works::

    from compas.scene import Scene
    import graph_drawing.rhino  # noqa: F401
    from graph_drawing import frames

    scene = Scene()
    scene.add(frames.drawing(json_path))
    geometry = scene.draw()

:func:`to_rhino` gives the geometry and the colours directly.
"""

from __future__ import absolute_import

from .conversion import RhinoDrawing
from .conversion import color
from .conversion import dash_pieces
from .conversion import to_rhino

SCENE_ERROR = None  # why the scene objects could not be registered, if they could not
try:
    from .scene import GHDrawingObject
    from .scene import RhinoDrawingObject
    from .scene import register_scene_objects
except Exception as e:  # the conversion above works without the COMPAS scene
    SCENE_ERROR = repr(e)

__all__ = ["RhinoDrawing", "to_rhino", "color", "dash_pieces", "SCENE_ERROR"]
if SCENE_ERROR is None:
    __all__ += ["GHDrawingObject", "RhinoDrawingObject", "register_scene_objects"]

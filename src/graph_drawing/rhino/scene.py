"""
Scene objects that draw a :class:`graph_drawing.drawing.Drawing` with
``compas.scene.Scene`` in Rhino and in Grasshopper (Rhino 8 only).

COMPAS finds the scene objects of its own packages through ``__all_plugins__``,
but only in packages whose name starts with "compas". So graph_drawing
registers its scene objects itself when :mod:`graph_drawing.rhino` is
imported, after making sure the COMPAS ones are registered first.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import Rhino  # type: ignore
import Rhino.Geometry as rg  # type: ignore
import scriptcontext as sc  # type: ignore
from compas.scene import context
from compas.scene import register
from compas_ghpython.scene import GHSceneObject
from compas_rhino.scene import RhinoSceneObject

from graph_drawing.drawing import Drawing

from .conversion import to_rhino

__all__ = ["GHDrawingObject", "RhinoDrawingObject", "register_scene_objects"]


class GHDrawingObject(GHSceneObject):
    """Draws a drawing as Grasshopper geometry.

    Parameters
    ----------
    plane : :rhino:`Rhino.Geometry.Plane`, optional
        The plane to draw on (default: World XY, lower left corner at its origin).
    unit : float, optional
        Size of one drawing unit in document units (default 1.0).

    Attributes
    ----------
    colors : list[System.Drawing.Color]
        One colour per piece of geometry of the last :meth:`draw`. Grasshopper
        scene objects return geometry only; pass these to a Custom Preview.

    """

    def __init__(self, plane=None, unit=1.0, **kwargs):
        super(GHDrawingObject, self).__init__(**kwargs)
        self.plane = plane
        self.unit = unit
        self.colors = []

    def draw(self):
        geometry, colors = to_rhino(self.item, self.plane, self.unit)
        self.colors = colors
        self._guids = geometry
        return self.guids


class RhinoDrawingObject(RhinoSceneObject):
    """Draws a drawing into the Rhino document, every piece in its own colour.

    Parameters
    ----------
    plane : :rhino:`Rhino.Geometry.Plane`, optional
        The plane to draw on (default: World XY, lower left corner at its origin).
    unit : float, optional
        Size of one drawing unit in document units (default 1.0).

    """

    def __init__(self, plane=None, unit=1.0, **kwargs):
        super(RhinoDrawingObject, self).__init__(**kwargs)
        self.plane = plane
        self.unit = unit

    def draw(self):
        geometry, colors = to_rhino(self.item, self.plane, self.unit)
        guids = []
        for g, c in zip(geometry, colors):
            attr = self.compile_attributes(name=self.item.name or "drawing")
            attr.ObjectColor = c
            attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
            if isinstance(g, rg.TextDot):
                guid = sc.doc.Objects.AddTextDot(g, attr)
            elif isinstance(g, rg.Brep):
                guid = sc.doc.Objects.AddBrep(g, attr)
            else:
                guid = sc.doc.Objects.AddMesh(g, attr)
            guids.append(guid)
        if self.group:
            self.add_to_group(self.group, guids)
        self._guids = guids
        return self.guids


def register_scene_objects():
    """Register the drawing scene objects for Rhino and Grasshopper."""
    if not context.ITEM_SCENEOBJECT:
        context.register_scene_objects()  # the COMPAS ones first, they are only loaded into an empty registry
    register(Drawing, GHDrawingObject, context="Grasshopper")
    register(Drawing, RhinoDrawingObject, context="Rhino")


register_scene_objects()

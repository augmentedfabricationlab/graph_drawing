"""
Drawings as Rhino geometry on a plane (Rhino 8 only).

Lines become thin ribbon meshes so they keep their weight in the viewport;
text becomes surfaces scaled to the exact height (TextDots when that fails).
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

import Rhino  # type: ignore
import Rhino.Geometry as rg  # type: ignore
import System.Drawing as sd  # type: ignore

from graph_drawing.drawing import hex_rgb

__all__ = ["RhinoDrawing", "to_rhino", "color", "dash_pieces"]


def color(hex_color, alpha=255):
    """A System.Drawing.Color from a hex colour.

    Parameters
    ----------
    hex_color : str
        A colour such as ``"#3070b3"``.
    alpha : int, optional
        Opacity from 0 to 255. Default 255.

    Returns
    -------
    System.Drawing.Color

    """
    r, g, b = hex_rgb(hex_color)
    return sd.Color.FromArgb(alpha, r, g, b)


def dash_pieces(pts, dash):
    """Split a polyline into the pieces of a dashed or dotted line.

    Parameters
    ----------
    pts : list[tuple[float, float]]
        The polyline, in drawing units.
    dash : str | None
        "dash", "dot", or None for a solid line.

    Returns
    -------
    list[list[tuple[float, float]]]
        The visible pieces.

    """
    if not dash:
        return [pts]
    on_len, off_len = (0.18, 0.10) if dash == "dash" else (0.04, 0.09)
    pieces, cur, on, left = [], [pts[0]], True, on_len
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        t0 = 0.0
        while seg - t0 > left:
            t0 += left
            q = (x0 + (x1 - x0) * t0 / seg, y0 + (y1 - y0) * t0 / seg)
            if on:
                cur.append(q)
                pieces.append(cur)
            cur = [q]
            on = not on
            left = on_len if on else off_len
        left -= seg - t0
        if on:
            cur.append((x1, y1))
    if on and len(cur) > 1:
        pieces.append(cur)
    return pieces


class RhinoDrawing(object):
    """Turns the items of a drawing into Rhino geometry on a plane.

    For every piece of geometry it remembers which item and which colour
    field it came from, so a highlighted copy of the items only recolours it.

    Parameters
    ----------
    plane : :rhino:`Rhino.Geometry.Plane`
        The plane of the drawing; drawing units run along its X and Y axes.
    unit : float
        Size of one drawing unit in document units.

    Attributes
    ----------
    geo : list
        Meshes, Breps (text) and TextDots.
    col : list[System.Drawing.Color]
        One colour per piece of geometry.
    src : list[tuple[int, str]]
        Item index and colour field per piece of geometry.
    text_failed : bool
        True if text had to fall back to TextDots.

    """

    def __init__(self, plane, unit):
        self.plane, self.unit = plane, unit
        self.geo, self.col, self.src = [], [], []
        self.text_failed = False
        self._src = (0, "fill")

    def P(self, p, z=0.0):
        return self.plane.PointAt(p[0] * self.unit, p[1] * self.unit, z * self.unit)

    def _add(self, g, hex_color):
        if g is not None:
            self.geo.append(g)
            self.col.append(color(hex_color))
            self.src.append(self._src)

    def fan(self, pts, hex_color, z):
        m = rg.Mesh()
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        m.Vertices.Add(self.P((cx, cy), z))
        for p in pts:
            m.Vertices.Add(self.P(p, z))
        n = len(pts)
        for i in range(n):
            m.Faces.AddFace(0, 1 + i, 1 + (i + 1) % n)
        m.Normals.ComputeNormals()
        self._add(m, hex_color)

    def ribbon(self, pts, width, hex_color, z, closed=False):
        if closed:
            pts = list(pts) + [pts[0], pts[1]]
        m = rg.Mesh()
        h = width / 2.0
        for i, (x, y) in enumerate(pts):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, len(pts) - 1)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / L * h, dx / L * h
            m.Vertices.Add(self.P((x + nx, y + ny), z))
            m.Vertices.Add(self.P((x - nx, y - ny), z))
        for i in range(len(pts) - 1):
            m.Faces.AddFace(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2)
        m.Normals.ComputeNormals()
        self._add(m, hex_color)

    def text(self, s, pos, size, hex_color, anchor, z):
        try:
            style = Rhino.DocObjects.DimensionStyle()
            try:
                style.Font = Rhino.DocObjects.Font.FromQuartetProperties("Times New Roman", False, False)
            except Exception:
                pass
            style.TextHeight = 1.0
            te = rg.TextEntity.Create(s, rg.Plane.WorldXY, style, False, 0, 0)
            breps = list(te.CreateSurfaces(style, 1.0, 0.0) or [])
            if not breps:
                raise RuntimeError("no text surfaces")
            bb = rg.BoundingBox.Empty
            for b in breps:
                bb.Union(b.GetBoundingBox(True))
            # scale to the wanted cap height, then place on the drawing plane
            cap = size * self.unit
            k = cap / max(bb.Max.Y - bb.Min.Y, 1e-9)
            w = (bb.Max.X - bb.Min.X) * k
            ox = {"middle": -w / 2.0, "end": -w}.get(anchor, 0.0)
            scale = rg.Transform.Scale(rg.Point3d(bb.Min.X, bb.Min.Y, 0), k)
            move = rg.Transform.Translation(rg.Vector3d(-bb.Min.X + ox, -bb.Min.Y - cap / 2.0, 0))
            target = rg.Plane(self.plane)
            target.Origin = self.P(pos, z)
            to_plane = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, target)
            for b in breps:
                b.Transform(scale)
                b.Transform(move)
                b.Transform(to_plane)
                self._add(b, hex_color)
        except Exception:
            self.text_failed = True
            self._add(rg.TextDot(s, self.P(pos, z)), hex_color)

    def draw(self, items, z0=0.0, first=0):
        """Add the geometry of the items. Returns the height of the last item."""
        z = z0
        for i, it in enumerate(items):
            i += first
            z += 0.0002  # later items slightly above earlier ones
            t = it["t"]
            if t == "circle":
                c, r = it["c"], it["r"]
                ring = [(c[0] + r * math.cos(2 * math.pi * k / 48), c[1] + r * math.sin(2 * math.pi * k / 48))
                        for k in range(48)]
                self._src = (i, "fill")
                self.fan(ring, it["fill"], z)
                if it.get("stroke"):
                    self._src = (i, "stroke")
                    self.ribbon(ring, it["w"], it["stroke"], z + 0.0002, closed=True)
            elif t == "poly":
                if it.get("fill"):
                    self._src = (i, "fill")
                    self.fan(it["pts"], it["fill"], z)
                if it.get("stroke"):
                    self._src = (i, "stroke")
                    pts = list(it["pts"]) + [it["pts"][0]]
                    for piece in dash_pieces(pts, it.get("dash")):
                        self.ribbon(piece, it["w"], it["stroke"], z)
            elif t == "line":
                self._src = (i, "color")
                for piece in dash_pieces(it["pts"], it.get("dash")):
                    self.ribbon(piece, it["w"], it["color"], z)
            elif t == "text":
                self._src = (i, "color")
                self.text(it["s"], it["pos"], it["size"], it["color"], it.get("anchor", "middle"), z + 0.001)
        return z

    def colors(self, items):
        """Colours of the geometry for another version of the same items (a focus)."""
        return [color(items[i][f]) for i, f in self.src]


def to_rhino(drawing, plane=None, unit=1.0, origin_at_corner=True):
    """A drawing as Rhino geometry and colours.

    Parameters
    ----------
    drawing : :class:`graph_drawing.drawing.Drawing`
        The drawing.
    plane : :rhino:`Rhino.Geometry.Plane`, optional
        The plane to draw on (default: World XY).
    unit : float, optional
        Size of one drawing unit in document units.
    origin_at_corner : bool, optional
        Put the lower left corner of the drawing at the plane's origin (default True).

    Returns
    -------
    tuple[list, list]
        The geometry and one System.Drawing.Color per piece.

    """
    plane = rg.Plane(plane) if plane is not None else rg.Plane.WorldXY
    if origin_at_corner:
        x0, y0 = drawing.bounds[0], drawing.bounds[1]
        plane.Origin = plane.PointAt(-x0 * unit, -y0 * unit)
    rd = RhinoDrawing(plane, unit)
    rd.draw(drawing.items)
    return rd.geo, rd.col

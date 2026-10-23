"""
Frames from JSON: parts as boxes, their contacts, which part
carries which, and the support graph drawn after Bruun et al. 2024
(Construction Robotics 8:20, Fig. 7).

Conventions of the JSON (schema 2.1.0, a three.js scene, Y up)
    origin      centre of the box
    dimensions  width along local X, height along local Y, depth along local Z
    rotation    Euler angles in radians, applied in three.js order "YXZ"
                (R = Ry * Rx * Rz). Checked against the corner model: with this
                order every listed connection touches, with "XYZ" the braces
                stand out of their wall plane.
Output coordinates are Rhino style (Z up, metres): (x, y, z)_three -> (x, -z, y).

Main functions
    load_parts      the parts of a JSON file as oriented boxes
    build_graph     the contact graph: listed and geometric connections, support directions
    drawing_graph   the contact graph styled for drawing, with one ground node per wall
    drawing         JSON to Drawing in one call
    report          the consistency check between JSON and geometry
    focus           how every part relates to a selected one

The same code runs in Rhino 8 (CPython 3.9) and in a plain Python for testing.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import math
import os

from compas.datastructures import Graph

from . import layouts
from .drawing import INK
from .drawing import INK_MUTED  # noqa: F401  (used by the Grasshopper component through this module)
from .drawing import R
from .drawing import blend  # noqa: F401  (used by the Grasshopper component through this module)
from .drawing import draw
from .drawing import hex_rgb  # noqa: F401
from .drawing import highlight as _highlight
from .drawing import text_on  # noqa: F401

__all__ = [
    "Part",
    "load_parts",
    "build_graph",
    "support_graph",
    "drawing_graph",
    "drawing",
    "scene",
    "edges",
    "edge_data",
    "report",
    "legend",
    "find_node",
    "unsupported_without",
    "focus",
    "focus_lines",
    "highlight",
    "TYPES",
    "TYPE",
    "TYPE_ORDER",
]

EULER_ORDER = "YXZ"
CONTACT_TOL = 0.005  # metres: boxes closer than this count as touching
GROUND = "ground"

# Member types: (keywords in the id, code letter, legend name, colour).
# Colours are the first slots of a validated colour-blind-safe categorical
# palette, in fixed order; the code letter carries the type as well, so colour
# is never the only cue.
TYPES = [
    ("sill", ("bottom_beam", "sill", "sole"), "S", "Sill", "#2a78d6"),
    ("post", ("post", "stud"), "P", "Post", "#eb6834"),
    ("rail", ("rail", "riegel", "header", "lintel", "sturz", "sill_plate_window"), "R", "Rail", "#1baf7a"),
    ("top", ("top_beam", "plate", "rahm"), "T", "Top beam", "#eda100"),
    ("brace", ("brace", "strebe"), "B", "Brace", "#e87ba4"),
    ("strut", ("strut",), "D", "Strut", "#008300"),
    ("joist", ("joist", "rafter", "purlin", "ridge", "balken"), "J", "Joist", "#6250d6"),
    ("other", (), "X", "Other", "#7a7a75"),
]
TYPE = {t[0]: {"keys": t[1], "letter": t[2], "name": t[3], "color": t[4]} for t in TYPES}
TYPE_ORDER = [t[0] for t in TYPES]

DEFECT = "#c0392b"
# model view: strong enough to read at a glance in a shaded viewport
PART_FILL = {"intact": "#ecebe7", "defective": "#d4483b", "missing": "#ffd23f"}
NEW_FILL = "#4fae5c"
MISSING_EDGE = "#d9a400"  # outline of missing parts (they are drawn transparent)
MISSING_ALPHA = 150
MISSING_TAG = "#ffe88a"  # tag of a missing part

# Focus on one part (click or `select`): role of every other part
ROLE_COLOR = {
    "sel": "#1d1d1b",     # the selected part
    "below": "#2f6fca",   # the selected part rests on it
    "above": "#e0662f",   # rests on the selected part
    "above2": "#f2b48f",  # loses all support from below once it is out (chain)
    "touch": "#8a8985",   # touches it, no load direction (or both carry each other)
}
ROLE_NAME = {"sel": "selected", "below": "rests on", "above": "carries",
             "above2": "loses support too", "touch": "touches"}
ROLE_ORDER = ("below", "above", "above2", "touch")

EDGE_STYLE = {          # how a connection is drawn
    "both": "solid",     # listed by both parts
    "one-sided": "dashed",  # listed by one part only
    "geometric": "dotted",  # touching, but listed by neither part
}

NOTE = ("arrow: rests on    solid: listed    dashed: listed by one part    "
        "dotted: touching, not listed    red ring: defective    yellow: missing    black ring: new")


# ==============================================================================
# Small linear algebra (no numpy, so the module has no binary dependencies)
# ==============================================================================


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _rot(axis, ang):
    c, s = math.cos(ang), math.sin(ang)
    if axis == "X":
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == "Y":
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def euler_matrix(rx, ry, rz, order=EULER_ORDER):
    """Rotation matrix like three.js Matrix4.makeRotationFromEuler."""
    angles = {"X": rx, "Y": ry, "Z": rz}
    m = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    for axis in order:
        m = _mat_mul(m, _rot(axis, angles[axis]))
    return m


def _yup_to_zup(v):
    return (v[0], -v[2], v[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

# ==============================================================================
# Parts
# ==============================================================================


def member_type(part_id, label=""):
    text = (part_id + " " + label).lower().replace(" ", "_")
    for key in TYPE_ORDER:
        if any(k in text for k in TYPE[key]["keys"]):
            return key
    return "other"


class Part(object):
    """One member as an oriented box, in Rhino coordinates (Z up, metres).

    Parameters
    ----------
    data : dict
        The part as it is stored in the JSON.
    order : str, optional
        Order of the Euler rotations. Default "YXZ".

    """

    def __init__(self, data, order=EULER_ORDER):
        self.data = data
        self.id = data["id"]
        self.label = data.get("label") or self.id
        self.status = (data.get("status") or "intact").lower()
        self.material = data.get("material") or ""
        self.notes = data.get("notes") or ""
        self.connections = list(data.get("connections") or [])
        self.type = member_type(self.id, self.label)
        o, d, r = data["origin"], data["dimensions"], data.get("rotation") or {}
        m = euler_matrix(r.get("x", 0.0), r.get("y", 0.0), r.get("z", 0.0), order)
        cols = [(m[0][i], m[1][i], m[2][i]) for i in range(3)]
        self.center = _yup_to_zup((o["x"], o["y"], o["z"]))
        self.axes = [_yup_to_zup(c) for c in cols]  # local X, Y, Z
        self.size = (d["width"], d["height"], d["depth"])
        self.half = tuple(0.5 * s for s in self.size)
        self.long = max(range(3), key=lambda i: self.size[i])
        self.code = self.id
        self.walls = []
        self.wall_u = {}
        self.wall_defs = []

    @property
    def long_axis(self):
        return self.axes[self.long]

    @property
    def verticality(self):
        return abs(self.long_axis[2])

    @property
    def is_new(self):
        text = (self.material + " " + self.notes).lower()
        return "new" in self.material.lower() or "not yet installed" in text

    def fill(self):
        """Colour of the part in the model view (by status)."""
        if self.is_new and self.status == "intact":
            return NEW_FILL
        return PART_FILL.get(self.status, PART_FILL["intact"])

    @property
    def color(self):
        """Colour of the node in the graph (by member type)."""
        return TYPE[self.type]["color"]

    def point(self, s):
        """Point at local coordinates s (each in -1..1, scaled by the half sizes)."""
        p = self.center
        for k in range(3):
            p = _add(p, self.axes[k], s[k] * self.half[k])
        return p

    def corners(self):
        return [self.point((sx, sy, sz)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

    def samples(self):
        return [self.point((a, b, c)) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]

    def closest(self, p):
        q = self.center
        d = _sub(p, self.center)
        for k in range(3):
            t = max(-self.half[k], min(self.half[k], _dot(d, self.axes[k])))
            q = _add(q, self.axes[k], t)
        return q

    def axial(self, p):
        """Position of p along the long axis, -1 at one end, +1 at the other."""
        return _dot(_sub(p, self.center), self.long_axis) / self.half[self.long]

    def zmin(self):
        return min(c[2] for c in self.corners())

    def zmax(self):
        return max(c[2] for c in self.corners())


def load_parts(source, order=EULER_ORDER):
    """The parts of a frame as oriented boxes.

    Parameters
    ----------
    source : str | dict
        Path to a JSON file, a JSON string or a parsed dict.
    order : str, optional
        Order of the Euler rotations. Default "YXZ".

    Returns
    -------
    list[:class:`Part`]
        With walls and codes assigned.

    """
    if isinstance(source, dict):
        data = source
    elif os.path.isfile(str(source)):
        with open(str(source), encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(source)
    parts = [Part(p, order) for p in data.get("instance", data).get("parts", [])]
    assign_walls_and_codes(parts)
    return parts

# ==============================================================================
# Contacts and support direction
# ==============================================================================


def box_gap(a, b):
    """Separating-axis test for two oriented boxes.

    Returns the largest gap along the 15 candidate axes: > 0 means apart by at
    least that much, <= 0 means touching or overlapping.
    """
    t = _sub(b.center, a.center)
    cands = list(a.axes) + list(b.axes)
    for u in a.axes:
        for v in b.axes:
            c = _cross(u, v)
            n = _norm(c)
            if n > 1e-9:
                cands.append((c[0] / n, c[1] / n, c[2] / n))
    best = -1e9
    for L in cands:
        ra = sum(a.half[i] * abs(_dot(a.axes[i], L)) for i in range(3))
        rb = sum(b.half[i] * abs(_dot(b.axes[i], L)) for i in range(3))
        best = max(best, abs(_dot(t, L)) - ra - rb)
    return best


def _sat_axis(a, b):
    """Axis of largest separation (the contact normal for touching boxes)."""
    t = _sub(b.center, a.center)
    cands = list(a.axes) + list(b.axes)
    for u in a.axes:
        for v in b.axes:
            c = _cross(u, v)
            n = _norm(c)
            if n > 1e-9:
                cands.append((c[0] / n, c[1] / n, c[2] / n))
    best = None
    for L in cands:
        ra = sum(a.half[i] * abs(_dot(a.axes[i], L)) for i in range(3))
        rb = sum(b.half[i] * abs(_dot(b.axes[i], L)) for i in range(3))
        gap = abs(_dot(t, L)) - ra - rb
        if best is None or gap > best[0] + 1e-12:
            best = (gap, L, ra, rb)
    return best


def _hull(pts):
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def _clip(subject, clipper):
    """Sutherland-Hodgman: convex polygon intersection (counter-clockwise)."""
    out = subject
    n = len(clipper)
    for i in range(n):
        a, b = clipper[i], clipper[(i + 1) % n]
        inp, out = out, []
        if not inp:
            break

        def inside(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-12

        def inter(p, q):
            x1, y1, x2, y2 = p[0], p[1], q[0], q[1]
            x3, y3, x4, y4 = a[0], a[1], b[0], b[1]
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-15:
                return q
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        for j in range(len(inp)):
            p, q = inp[j], inp[(j + 1) % len(inp)]
            if inside(q):
                if not inside(p):
                    out.append(inter(p, q))
                out.append(q)
            elif inside(p):
                out.append(inter(p, q))
    return out


def contact(a, b, tol=CONTACT_TOL):
    """Contact point between two touching boxes and its kind.

    Both boxes are projected along the contact normal (the separating axis
    with the largest gap); the overlap of the two outlines is the contact
    patch. kind is "face" for a patch of at least 2 cm2, "edge" for a strip
    longer than 2 cm, "point" otherwise. The contact point is the centre of the
    patch, halfway between the two facing faces.
    """
    gap, L, ra, rb = _sat_axis(a, b)
    if _dot(_sub(b.center, a.center), L) < 0:
        L = (-L[0], -L[1], -L[2])
    ref = (1.0, 0.0, 0.0) if abs(L[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _cross(L, ref)
    n1 = _norm(e1)
    e1 = (e1[0] / n1, e1[1] / n1, e1[2] / n1)
    e2 = _cross(L, e1)
    pa = _hull([(_dot(c, e1), _dot(c, e2)) for c in a.corners()])
    pb = _hull([(_dot(c, e1), _dot(c, e2)) for c in b.corners()])
    poly = _clip(pa, pb) if len(pa) >= 3 and len(pb) >= 3 else []
    h = (_dot(a.center, L) + ra + _dot(b.center, L) - rb) / 2.0
    if len(poly) >= 3:
        area = 0.0
        cx = cy = 0.0
        for i in range(len(poly)):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % len(poly)]
            cr = x0 * y1 - x1 * y0
            area += cr
            cx += (x0 + x1) * cr
            cy += (y0 + y1) * cr
        area /= 2.0
        if abs(area) > 1e-12:
            cx, cy = cx / (6 * area), cy / (6 * area)
        else:
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
        area = abs(area)
        span = max(math.hypot(p[0] - q[0], p[1] - q[1]) for p in poly for q in poly)
    else:
        pts = poly or pa
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        area, span = 0.0, 0.0
    c = _add(_add((e1[0] * cx, e1[1] * cx, e1[2] * cx), e2, cy), L, h)
    kind = "face" if area >= 2e-4 else ("edge" if span >= 0.02 else "point")
    # where along the members they meet: centre of the sample points of each
    # box that lie on (or in) the other box; more robust for ends that cut
    # into the other member than the patch centre
    pts = [q for q in a.samples() if _norm(_sub(q, b.closest(q))) <= 2 * tol]
    pts += [q for q in b.samples() if _norm(_sub(q, a.closest(q))) <= 2 * tol]
    if pts:
        c = tuple(sum(q[k] for q in pts) / len(pts) for k in range(3))
    return c, kind


def support_direction(a, b, c):
    """Which part carries which, from where they touch.

    Returns (supported, supporter), "both" for two horizontal members joined
    end to end (a corner), or None when nothing can be said.
    Rules: a member whose end meets the middle of another is framed into it and
    carried by it, unless it is a post-like member meeting a horizontal member
    with its upper end; then the horizontal member rests on it.
    """
    ta, tb = a.axial(c), b.axial(c)
    end_a, end_b = abs(ta) > 0.8, abs(tb) > 0.8
    vert_a, vert_b = a.verticality > 0.6, b.verticality > 0.6

    def framed(f, host):
        upper = _dot(_sub(c, f.center), (0, 0, 1)) > 0
        if f.verticality > 0.6 and upper and host.verticality <= 0.6:
            return (host.id, f.id)  # horizontal host rests on the post
        return (f.id, host.id)

    if end_a and not end_b:
        return framed(a, b)
    if end_b and not end_a:
        return framed(b, a)
    if end_a and end_b:
        if vert_a and not vert_b:
            return framed(a, b)
        if vert_b and not vert_a:
            return framed(b, a)
        return "both"
    return None

# ==============================================================================
# Walls and short codes
# ==============================================================================


WALL_WORDS = ("front", "back", "side", "left", "right", "north", "south", "east", "west")


def assign_walls_and_codes(parts, tol=0.15):
    """Group parts into vertical wall planes and give each a short code.

    Wall planes are spanned by the sills and top beams (vertical planes through
    their long axes); without such members any horizontal or inclined member
    may define one. Planes closer than tol are merged. A part belongs to every
    wall plane that passes through it and that it does not cross, so corner
    posts belong to two walls. Every wall gets an outward normal (away from the
    middle of the structure, in plan) and a direction along it, left to right
    for someone standing outside.

    Codes follow Bruun et al.: wall letter + type letter + number along the
    wall, e.g. FR3 = front wall, rail 3. Parts in two walls get C (corner),
    parts in no wall get O (other, e.g. joists).
    """
    if not parts:
        return []
    cx = sum(p.center[0] for p in parts) / len(parts)
    cy = sum(p.center[1] for p in parts) / len(parts)

    def horizontal(p):
        h = (p.long_axis[0], p.long_axis[1], 0.0)
        return h if _norm(h) >= 0.3 else None

    definers = [p for p in parts if p.type in ("sill", "top") and horizontal(p)]
    if not definers:
        definers = [p for p in parts if horizontal(p) and p.type != "joist"]
    planes = []  # [normal, offset, n]
    for p in definers:
        h = horizontal(p)
        n = _norm(h)
        nrm = (-h[1] / n, h[0] / n, 0.0)
        if nrm[0] < -1e-9 or (abs(nrm[0]) < 1e-9 and nrm[1] < 0):
            nrm = (-nrm[0], -nrm[1], 0.0)
        off = _dot(nrm, p.center)
        for pl in planes:
            if abs(_dot(pl[0], nrm)) > 0.95 and abs(pl[1] - off) < tol:
                pl[2] += 1
                break
        else:
            planes.append([nrm, off, 1])

    byid = {p.id: p for p in parts}
    walls = []
    for k, (nrm, off, _) in enumerate(planes):
        members = []
        for p in parts:
            if abs(_dot(p.long_axis, nrm)) > 0.5:
                continue  # runs across the plane, e.g. the other wall's sill
            extent = sum(p.half[i] * abs(_dot(p.axes[i], nrm)) for i in range(3))
            if abs(_dot(nrm, p.center) - off) <= extent + 0.01:
                members.append(p.id)
        if len(members) < 2:
            continue
        # outward normal: away from the middle of the structure
        side = _dot(nrm, (cx, cy, 0.0)) - off
        out = (-nrm[0], -nrm[1], 0.0) if side > 0 else nrm
        along = (-out[1], out[0], 0.0)  # left to right, seen from outside
        words = {}
        for m in members:
            for w in WALL_WORDS:
                if w in m.split("_"):
                    words[w] = words.get(w, 0) + 1
        name = max(words, key=words.get) if words else "wall %d" % (k + 1)
        walls.append({"name": name, "normal": out, "along": along, "offset": off, "members": members})
    seen = {}
    for w in walls:
        if w["name"] in seen:
            seen[w["name"]] += 1
            w["name"] = "%s %d" % (w["name"], seen[w["name"]])
        else:
            seen[w["name"]] = 1
    for p in parts:
        p.walls, p.wall_u = [], {}
    for w in walls:
        for m in w["members"]:
            byid[m].walls.append(w["name"])
            byid[m].wall_u[w["name"]] = _dot(byid[m].center, w["along"])
    for p in parts:
        p.wall_defs = walls

    # codes, numbered along the wall (corner and other parts: around the middle)
    groups = {}
    for p in parts:
        if len(p.walls) == 1:
            wl = p.walls[0][0].upper()
            key = p.wall_u[p.walls[0]]
        else:
            wl = "C" if len(p.walls) > 1 else "O"
            key = math.atan2(p.center[1] - cy, p.center[0] - cx)
        groups.setdefault((wl, p.type), []).append((key, -p.center[2], p))
    for (wl, t), ps in groups.items():
        ps.sort(key=lambda e: (round(e[0], 3), e[1]))
        letter = TYPE[t]["letter"]
        for i, (_, _, p) in enumerate(ps):
            p.code = wl + letter + (str(i + 1) if len(ps) > 1 else "")
    return walls


# ==============================================================================
# Contact graph
# ==============================================================================


def edge_data(g, u, v):
    """Attributes of the edge between two nodes, in whichever direction it is stored.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.
    u : str
        One node.
    v : str
        The other node.

    Returns
    -------
    dict

    """
    if v in g.edge.get(u, {}):
        return g.edge[u][v]
    return g.edge[v][u]


def edges(g):
    """Every connection of the contact graph, once.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.

    Yields
    ------
    tuple
        ``(u, v, attributes)``, from the first of the two nodes in node order,
        neighbours in the order they were connected.

    """
    seen = set()
    for n in g.nodes():
        for m in g.adjacency[n]:
            if m not in seen:
                yield n, m, edge_data(g, n, m)
        seen.add(n)


def build_graph(parts, tol=CONTACT_TOL, geometric_edges=True):
    """Graph of the parts and their contacts.

    Parameters
    ----------
    parts : list[:class:`Part`]
        The parts, as from :func:`load_parts`.
    tol : float, optional
        Boxes closer than this (metres) count as touching.
    geometric_edges : bool, optional
        Also add face contacts the JSON does not list.

    Returns
    -------
    :class:`compas.datastructures.Graph`
        Node per part id with label, code, type, walls, wall_u, status, material,
        notes, center, size, fill (model colour), color (type colour), new.
        Edge attributes:

        * kind: "both" | "one-sided" | "geometric"
        * touching: True if the boxes touch within tol
        * gap: box gap in metres (negative = overlap)
        * contact: contact point (or None), contact_kind: "face" | "edge" | "point"
        * support: (supported, supporter), "both" or None

        Parts standing on the lowest level get an edge to the node "ground".
        Contacts only along an edge or a point stay out of the graph when the
        JSON does not list them (they are reported). The graph attributes hold
        unknown_connections, weak_contacts, contact_tol and walls.

    """
    g = Graph(name="contacts")
    byid = {p.id: p for p in parts}
    for p in parts:
        g.add_node(p.id, label=p.label, code=p.code, type=p.type, walls=list(p.walls), wall_u=dict(p.wall_u),
                   status=p.status, material=p.material, notes=p.notes, center=p.center,
                   size=p.size, fill=p.fill(), color=p.color, new=p.is_new)

    def add(a, b, kind):
        gap = box_gap(a, b)
        d = dict(kind=kind, gap=gap, touching=gap <= tol, contact=None,
                 contact_kind=None, support=None)
        if gap <= tol:
            c, ck = contact(a, b, tol)
            d.update(contact=c, contact_kind=ck, support=support_direction(a, b, c))
        g.add_edge(a.id, b.id, **d)

    unknown = []
    for p in parts:
        for q in p.connections:
            if q not in byid:
                unknown.append((p.id, q))
            elif q != p.id and not g.has_edge((p.id, q), directed=False):
                add(p, byid[q], "both" if p.id in byid[q].connections else "one-sided")

    weak = []
    if geometric_edges:
        for i, a in enumerate(parts):
            for b in parts[i + 1:]:
                if g.has_edge((a.id, b.id), directed=False) or box_gap(a, b) > tol:
                    continue
                c, ck = contact(a, b, tol)
                if ck == "face":
                    add(a, b, "geometric")
                else:
                    weak.append((a.id, b.id, ck))

    zmin = min(p.zmin() for p in parts) if parts else 0.0
    grounded = [p for p in parts if p.zmin() <= zmin + tol]
    if grounded:
        g.add_node(GROUND, label="Ground", code="G", type="ground", walls=[], wall_u={}, status="intact",
                   material="", notes="", center=(0, 0, zmin), size=(0, 0, 0),
                   fill="#000000", color="#000000", new=False)
        for p in grounded:
            g.add_edge(p.id, GROUND, kind="both", gap=0.0, touching=True,
                       contact=(p.center[0], p.center[1], zmin), contact_kind="face",
                       support=(p.id, GROUND))

    g.attributes.update(unknown_connections=unknown, weak_contacts=weak, contact_tol=tol,
                        walls=[{k: v for k, v in w.items() if k != "members"} for w in (parts[0].wall_defs if parts else [])])
    return g


def support_graph(g):
    """Directed graph of the support relations.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.

    Returns
    -------
    :class:`compas.datastructures.Graph`
        An edge u -> v means u rests on v, the load path as in Bruun et al.
        Two parts that carry each other get edges in both directions.

    """
    d = Graph(name="support")
    for n in g.nodes():
        d.add_node(n, **dict(g.node[n]))
    for u, v, e in edges(g):
        s = e.get("support")
        if s == "both":
            d.add_edge(u, v, **dict(e))
            d.add_edge(v, u, **dict(e))
        elif s:
            d.add_edge(s[0], s[1], **dict(e))
    return d


def edge_color(g, u, v, data):
    """Edges take the colour of the carried member (as in Bruun et al.)."""
    if data.get("kind") != "geometric" and not data.get("touching", True):
        return DEFECT
    s = data.get("support")
    src = s[0] if isinstance(s, (tuple, list)) else u
    return g.node[src].get("color", INK) if src != GROUND else INK


def report(g):
    """A plain-text summary with the inconsistencies between JSON and geometry.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.

    Returns
    -------
    str

    """
    parts = [n for n in g.nodes() if n != GROUND]
    all_edges = list(edges(g))
    lines = []
    kinds = {}
    for u, v, d in all_edges:
        if GROUND not in (u, v):
            kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    lines.append("parts: %d   connections: %d   (%s)" % (
        len(parts), sum(kinds.values()), ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
    status = {}
    for n in parts:
        s = g.node[n]["status"]
        status[s] = status.get(s, 0) + 1
    lines.append("status: " + ", ".join("%s %d" % kv for kv in sorted(status.items())))
    new = [g.node[n]["code"] for n in parts if g.node[n].get("new")]
    if new:
        lines.append("new parts: " + ", ".join(new))
    if g.has_node(GROUND):
        lines.append("on the ground: " + ", ".join(g.node[n]["code"] for n in g.neighbors(GROUND)))

    def c(n):
        return "%s (%s)" % (g.node[n]["code"], n)

    iso = [n for n in parts if not any(edge_data(g, n, m)["kind"] != "geometric" for m in g.neighbors(n))]
    if iso:
        lines.append("no listed connection: " + ", ".join(c(n) for n in iso))
    one = [(u, v) for u, v, d in all_edges if d["kind"] == "one-sided"]
    if one:
        lines.append("listed by one side only: " + "; ".join("%s - %s" % (c(u), c(v)) for u, v in one))
    apart = [(u, v, d["gap"]) for u, v, d in all_edges
             if d["kind"] != "geometric" and not d["touching"]]
    if apart:
        lines.append("listed but not touching: " + "; ".join(
            "%s - %s (%.0f mm)" % (c(u), c(v), 1000 * gap) for u, v, gap in apart))
    geo = [(u, v) for u, v, d in all_edges if d["kind"] == "geometric"]
    if geo:
        lines.append("touching but not listed: " + "; ".join("%s - %s" % (c(u), c(v)) for u, v in geo))
    if g.attributes.get("weak_contacts"):
        lines.append("only edge or point contact, left out: " + "; ".join(
            "%s - %s" % (c(u), c(v)) for u, v, _ in g.attributes["weak_contacts"]))
    undirected = [(u, v) for u, v, d in all_edges if d.get("touching") and d.get("support") is None]
    if undirected:
        lines.append("no support direction found: " + "; ".join("%s - %s" % (c(u), c(v)) for u, v in undirected))
    if g.attributes.get("unknown_connections"):
        lines.append("unknown ids: " + "; ".join("%s -> %s" % tuple(e) for e in g.attributes["unknown_connections"]))
    return "\n".join(lines)


def legend(g):
    """The codes of all parts and their ids, as text.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.

    Returns
    -------
    str
        One line per part, ``code id``.

    """
    rows = sorted((g.node[n]["code"], n) for n in g.nodes())
    return "\n".join("%-5s %s" % r for r in rows)


# ==============================================================================
# Drawing
# ==============================================================================


def drawing_graph(g):
    """The contact graph styled for :func:`graph_drawing.drawing.draw`.

    Every connection becomes an edge from the carried part to the carrying one
    (arrowheads at both ends where two parts carry each other), coloured like
    the carried part, solid when both parts list it, dashed when one does,
    dotted when neither does. The ground is drawn once per wall, like the
    foundation nodes in Bruun's figure: the node "ground:<wall>" stands for the
    ground under that wall. The keys of the original edges are kept under
    "source", so a focus on the contact graph can be shown on the drawing.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.

    Returns
    -------
    :class:`compas.datastructures.Graph`
        Ready for :func:`graph_drawing.layouts.support` and :func:`graph_drawing.drawing.draw`.

    """
    dg = Graph(name="support drawing")
    walls = g.attributes.get("walls", [])
    dg.attributes["walls"] = walls
    for n in g.nodes():
        if n == GROUND:
            continue
        nd = g.node[n]
        fill = nd.get("color", "#7a7a75")
        status = nd.get("status")
        stroke, w, txt = None, 0.0, text_on(fill)
        if status == "missing":
            stroke, w, txt, fill = fill, 0.04, INK, MISSING_TAG
        if status == "defective":
            stroke, w = DEFECT, 0.09
        if nd.get("new"):
            stroke, w = INK, 0.06
        outline = R + 0.045 if status == "defective" else (R + 0.03 if nd.get("new") else R)
        dg.add_node(n, label=nd.get("code", n), fill=fill, stroke=stroke, stroke_width=w, text_color=txt,
                    outline=outline, type=nd.get("type"), walls=list(nd.get("walls", [])),
                    wall_u=dict(nd.get("wall_u", {})), center=nd.get("center"), status=status, new=nd.get("new"))
    single = set()
    for n in dg.nodes():
        ws = dg.node[n].get("walls", [])
        if len(ws) == 1:
            single.add(ws[0])
    for wall in walls:
        if wall["name"] in single:
            dg.add_node("%s:%s" % (GROUND, wall["name"]), label="", shape="triangle", fill="#000000",
                        ground=wall["name"], fixed=True)

    def wall_of(n):
        ws = g.node[n].get("walls", [])
        return ws[0] if ws else None

    for i, (u, v, d) in enumerate(edges(g)):
        s = d.get("support")
        a, b = (s[0], s[1]) if isinstance(s, (tuple, list)) else (u, v)
        if b == GROUND:
            b = "%s:%s" % (GROUND, wall_of(a))
        if a == GROUND:
            a = "%s:%s" % (GROUND, wall_of(b))
        if not (dg.has_node(a) and dg.has_node(b)):
            continue
        arrow = "both" if s == "both" else ("head" if s is not None else None)
        dg.add_edge(a, b, color=edge_color(g, u, v, d), dash={"one-sided": "dash", "geometric": "dot"}.get(d.get("kind")),
                    arrow=arrow, source=(u, v), order=i)
    return dg


def scene(g, title=None):
    """The support drawing of a contact graph as (items, bounds).

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        A contact graph from :func:`build_graph`.
    title : str, optional
        Title in the upper left corner.

    Returns
    -------
    tuple[list[dict], tuple]

    """
    d = support_drawing(g, title)
    return d.items, d.bounds


def support_drawing(g, title=None):
    """The support drawing of a contact graph as a :class:`graph_drawing.drawing.Drawing`."""
    dg = drawing_graph(g)
    pos, regions = layouts.support(dg)
    used = [t for t in TYPE_ORDER if any(g.node[n].get("type") == t for n in g.nodes())]
    entries = [(TYPE[t]["color"], "%s %s" % (TYPE[t]["letter"], TYPE[t]["name"])) for t in used]
    return draw(dg, pos, regions, title=title, legend=entries, note=NOTE)


def drawing(source, title=None, geometric_edges=True):
    """Read a JSON of parts and draw its support graph.

    Parameters
    ----------
    source : str or dict
        Path to a JSON file, a JSON string or a parsed dict.
    title : str, optional
        Title of the drawing. Defaults to the file name.
    geometric_edges : bool, optional
        Also show face contacts the JSON does not list.

    Returns
    -------
    :class:`graph_drawing.drawing.Drawing`

    """
    if title is None and not isinstance(source, dict) and os.path.isfile(str(source)):
        title = os.path.splitext(os.path.basename(str(source)))[0]
    g = build_graph(load_parts(source), geometric_edges=geometric_edges)
    return support_drawing(g, title)


def highlight(items, f):
    """The items of a support drawing, recoloured for a focus.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.
    f : dict
        A focus, from :func:`focus`.

    Returns
    -------
    list[dict]

    """
    return _highlight(items, f, ROLE_COLOR)


# ==============================================================================
# Focus on one part
# ==============================================================================


def find_node(g, s):
    """The node of a part, found by its id or its code. Case does not matter.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.
    s : str
        Id or code.

    Returns
    -------
    str | None

    """
    s = str(s or "").strip()
    if not s:
        return None
    if g.has_node(s) and s != GROUND:
        return s
    low = s.lower()
    for n in g.nodes():
        if n != GROUND and (n.lower() == low or str(g.node[n].get("code", "")).lower() == low):
            return n
    return None


def unsupported_without(g, sel):
    """Parts that lose all their support from below when sel is taken out.

    Fixpoint over the support relations: a part drops out when every part it
    rests on has dropped out. A part with another support left (a corner post
    that also stands on the other sill, a top beam that also rests on the
    other wall) stays. Mutual contacts (sills and top beams carrying each
    other at a corner) carry nothing here.
    Only gravity is read: rails held in the posts by tenons, or posts hanging
    from the top beam, count as unsupported all the same.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.
    sel : str
        The part taken out.

    Returns
    -------
    list[str]
        In the order they drop out.

    """
    rests = {}
    for u, v, d in edges(g):
        s = d.get("support")
        if isinstance(s, (tuple, list)):
            rests.setdefault(s[0], set()).add(s[1])
    gone = [sel]
    out = {sel}
    changed = True
    while changed:
        changed = False
        for n, sup in rests.items():
            if n not in out and n != GROUND and sup and sup <= out:
                out.add(n)
                gone.append(n)
                changed = True
    return gone[1:]


def focus(g, sel, chain=False):
    """How every part relates to the selected one.

    Roles are the direct contacts: what the part rests on, what rests on it,
    what only touches it. "affected" are the parts that lose all support from
    below when it is taken out, see :func:`unsupported_without`.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.
    sel : str
        The selected part.
    chain : bool, optional
        Also give the affected parts that are not direct contacts the role
        "above2", and keep their edges.

    Returns
    -------
    dict | None
        ``{"sel": id, "roles": {node: role}, "edges": set of node pairs,
        "affected": [ids], "chain": chain}``, or None if nothing is selected.

    """
    if sel is None or not g.has_node(sel):
        return None
    roles = {sel: "sel"}
    fedges = set()
    for v in g.neighbors(sel):
        s = edge_data(g, sel, v).get("support")
        if isinstance(s, (tuple, list)):
            role = "below" if s[0] == sel else "above"
        else:
            role = "touch"
        roles.setdefault(v, role)
        fedges.add(frozenset((sel, v)))
    affected = unsupported_without(g, sel)
    if chain:
        aset = set(affected) | {sel}
        for n in affected:
            roles.setdefault(n, "above2")
        for u, v, d in edges(g):
            s = d.get("support")
            if isinstance(s, (tuple, list)) and s[0] in aset and s[1] in aset:
                fedges.add(frozenset((u, v)))
    return {"sel": sel, "roles": roles, "edges": fedges, "affected": affected, "chain": chain}


def focus_lines(g, f):
    """A short description of a focus, line by line.

    Parameters
    ----------
    g : :class:`compas.datastructures.Graph`
        The contact graph of :func:`build_graph`.
    f : dict
        A focus, from :func:`focus`.

    Returns
    -------
    list[tuple]
        ``(role or None, text)`` per line.

    """
    if not f:
        return []
    sel = f["sel"]
    d = g.node[sel]
    kind = TYPE.get(d.get("type"), TYPE["other"])["name"].lower()
    head = "%s  %s  (%s, %s%s)" % (d.get("code", sel), sel, kind, d.get("status", ""), ", new" if d.get("new") else "")
    lines = [("sel", head)]
    for role in ROLE_ORDER:
        ns = [n for n, r in f["roles"].items() if r == role]
        if role == "above2" and not ns:
            continue
        codes = sorted(g.node[n].get("code", n) for n in ns)
        lines.append((role, "%s: %s" % (ROLE_NAME[role], ", ".join(codes) if codes else "-")))
    if f["affected"]:
        codes = sorted(g.node[n].get("code", n) for n in f["affected"])
        lines.append((None,
                      "without support from below once it is out: " + ", ".join(codes)))
    notes = (d.get("notes") or "").strip()
    if notes:
        lines.append((None, "notes: " + (notes if len(notes) <= 90 else notes[:87] + "...")))
    return lines

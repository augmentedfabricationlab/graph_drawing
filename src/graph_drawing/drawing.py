"""
Drawings: a graph with positions, turned into plain primitives.

A drawing is a list of items in abstract units (y up), so the same picture can
be rendered as Rhino geometry, on the Grasshopper canvas, as SVG and as PDF.

Items
    {"t": "circle", "c": (x, y), "r": r, "fill": hex, "stroke": hex | None, "w": w}
    {"t": "poly",   "pts": [...], "fill": hex | None, "stroke": hex | None, "w": w, "dash": None | "dash" | "dot"}
    {"t": "line",   "pts": [...], "color": hex, "w": w, "dash": None | "dash" | "dot"}
    {"t": "text",   "s": str, "pos": (x, y), "size": h, "color": hex,
                    "anchor": "middle" | "start" | "end", "bold": bool}

Items of a node carry its key under "n", items of an edge the edge under "e",
so a drawing can be recoloured for a focus without drawing it again.

Node attributes read by :func:`draw`
    label        text in the node (default: the key)
    fill         fill colour (default grey)
    stroke       ring colour, stroke_width its width
    text_color   label colour (default: black or white, whichever reads better)
    label_size   label height (default 0.19), bold (default True)
    shape        "circle" (default), "octagon" or "box"
    radius       circle radius (default R), width and height for boxes
    outline      radius where arrow tips end (default: the outer edge of the ring)
    fixed        True: the node never fades in a focus (ground nodes)

Edge attributes read by :func:`draw`
    color        line colour, width its width
    dash         None, "dash" or "dot"
    arrow        "head" (arrow at the second node), "both" or None
    source       the edge this one stands for, kept on its items under "e"
    order        drawing order of the edges (default: the order of the graph)
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

from compas.data import Data

__all__ = [
    "Drawing",
    "draw",
    "bounds",
    "highlight",
    "pick",
    "node_positions",
    "blend",
    "hex_rgb",
    "text_on",
    "route_edges",
    "arc",
]


R = 0.30      # node radius
EDGE_W = 0.03
ARROW = 0.17  # arrow length
FADE = 0.82   # how far unrelated items fade towards white in a focus

INK = "#0b0b0b"
INK_MUTED = "#8a8985"
GREY = "#7a7a75"

BOWS = (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.45, -0.45, 0.6, -0.6)


# ==============================================================================
# Colours
# ==============================================================================


def hex_rgb(h):
    """Red, green and blue of a hex colour.

    Parameters
    ----------
    h : str
        A colour such as ``"#3070b3"``.

    Returns
    -------
    tuple[int, int, int]
        Each from 0 to 255.

    """
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def text_on(fill):
    """Black or white text, whichever reads better on the fill.

    Parameters
    ----------
    fill : str
        Hex colour of the background.

    Returns
    -------
    str
        Hex colour of the text.

    """
    r, g, b = [c / 255.0 for c in hex_rgb(fill)]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#ffffff" if lum < 0.45 else INK


def blend(h, f, to="#ffffff"):
    """A colour moved part of the way towards another.

    Parameters
    ----------
    h : str
        Hex colour.
    f : float
        Fraction of the way, from 0 (``h``) to 1 (``to``).
    to : str, optional
        Hex colour to move towards. Default white.

    Returns
    -------
    str
        Hex colour.

    """
    a, b = hex_rgb(h), hex_rgb(to)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * f)) for i in range(3))


# ==============================================================================
# Drawing
# ==============================================================================


class Drawing(Data):
    """A drawing as a list of primitive items with its bounds.

    Parameters
    ----------
    items : list[dict], optional
        The primitive items (see the module docstring).
    bounds : tuple[float, float, float, float], optional
        x0, y0, x1, y1 of the drawing. Computed from the items when not given.
    title : str, optional
        The title of the drawing.

    Attributes
    ----------
    items : list[dict]
        The primitive items.
    bounds : tuple[float, float, float, float]
        x0, y0, x1, y1 of the drawing.
    title : str or None
        The title of the drawing.

    """

    DATASCHEMA = {
        "type": "object",
        "properties": {
            "items": {"type": "array"},
            "bounds": {"type": "array"},
            "title": {"type": ["string", "null"]},
        },
        "required": ["items", "bounds"],
    }

    @property
    def __data__(self):
        return {"items": self.items, "bounds": list(self.bounds), "title": self.title}

    @classmethod
    def __from_data__(cls, data):
        return cls(items=data["items"], bounds=data["bounds"], title=data.get("title"))

    def __init__(self, items=None, bounds=None, title=None, name=None):
        super(Drawing, self).__init__(name=name or title)
        self.items = list(items or [])
        if bounds is None:
            bounds = _items_bounds(self.items) if self.items else (0.0, 0.0, 1.0, 1.0)
        self.bounds = tuple(bounds)
        self.title = title

    def __str__(self):
        return "Drawing with {} items.".format(len(self.items))

    # ==========================================================================
    # Methods
    # ==========================================================================

    def highlighted(self, focus, colors=None):
        """A copy of the drawing with a focus (see :func:`highlight`)."""
        return Drawing(highlight(self.items, focus, colors), self.bounds, self.title)

    def pick(self, x, y, slack=0.08):
        """Key of the node under the drawing point (x, y), or None."""
        return pick(self.items, x, y, slack)

    def to_svg(self, scale=60.0, font="Times New Roman"):
        """The drawing as SVG text."""
        from .export import to_svg
        return to_svg(self.items, self.bounds, scale, font)

    def to_pdf(self, path, scale=28.0):
        """Write the drawing as a one-page PDF. Returns the path."""
        from .export import to_pdf
        return to_pdf(self.items, self.bounds, path, scale)


# ==============================================================================
# Curves
# ==============================================================================


def _qbez(p0, c, p1, n=80):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1])
            for t in (i / float(n) for i in range(n + 1))]


def _cut_start(pts, r):
    """Drop the part of the polyline within distance r of its first point,
    with the new start exactly on that circle."""
    a = pts[0]
    for i in range(1, len(pts)):
        d0 = math.hypot(pts[i - 1][0] - a[0], pts[i - 1][1] - a[1])
        d1 = math.hypot(pts[i][0] - a[0], pts[i][1] - a[1])
        if d1 >= r:
            f = (r - d0) / (d1 - d0) if d1 > d0 else 0.0
            p = (pts[i - 1][0] + f * (pts[i][0] - pts[i - 1][0]), pts[i - 1][1] + f * (pts[i][1] - pts[i - 1][1]))
            return [p] + pts[i:]
    return pts[-1:]


def _cut_end(pts, r):
    return list(reversed(_cut_start(list(reversed(pts)), r)))


def _cut_start_box(pts, hw, hh):
    """Drop the part of the polyline inside the box of half width hw and half
    height hh around its first point, with the new start on the box outline."""
    a = pts[0]

    def inside(p):
        return abs(p[0] - a[0]) < hw and abs(p[1] - a[1]) < hh
    for i in range(1, len(pts)):
        if not inside(pts[i]):
            p, q = pts[i - 1], pts[i]
            lo, hi = 0.0, 1.0
            for _ in range(30):
                m = (lo + hi) / 2.0
                if inside((p[0] + m * (q[0] - p[0]), p[1] + m * (q[1] - p[1]))):
                    lo = m
                else:
                    hi = m
            return [(p[0] + hi * (q[0] - p[0]), p[1] + hi * (q[1] - p[1]))] + pts[i:]
    return pts[-1:]


def _cut_end_box(pts, hw, hh):
    return list(reversed(_cut_start_box(list(reversed(pts)), hw, hh)))


def arc(p, q, bow):
    """A quadratic arc from p to q, bulging sideways.

    Parameters
    ----------
    p : tuple[float, float]
        Start point.
    q : tuple[float, float]
        End point.
    bow : float
        Bulge as a fraction of the distance from p to q. 0 is straight, the sign picks the side.

    Returns
    -------
    list[tuple[float, float]]
        Points along the arc.

    """
    mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    c = (mx + nx * bow * L, my + ny * bow * L)
    return _qbez(p, c, q)


def _clearance(pts, obstacles):
    """Smallest distance from the curve to any obstacle point."""
    best = float("inf")
    for i in range(1, len(pts)):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        vx, vy = bx - ax, by - ay
        vv = vx * vx + vy * vy or 1e-12
        for ox, oy in obstacles:
            f = max(0.0, min(1.0, ((ox - ax) * vx + (oy - ay) * vy) / vv))
            best = min(best, math.hypot(ax + f * vx - ox, ay + f * vy - oy))
    return best


def _seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _n_cross(pa, ba, pb, bb):
    """Crossings between two coarse polylines (with their bounding boxes)."""
    if ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1]:
        return 0
    n = 0
    for i in range(1, len(pa)):
        for j in range(1, len(pb)):
            if _seg_cross(pa[i - 1], pa[i], pb[j - 1], pb[j]):
                n += 1
    return n


def route_edges(ends, pos, need):
    """Pick a bow per edge: straight when that is clear, otherwise the curve
    that avoids nodes first and other edges second, as gently as possible.

    Parameters
    ----------
    ends : list[tuple]
        The (a, b) node keys of every edge.
    pos : dict
        Position (x, y) per node key; every node is an obstacle.
    need : float
        Distance a curve should keep from the nodes it passes.

    Returns
    -------
    list[float]
        One bow per edge, for :func:`arc`.

    """
    pts = [pos[n] for n in pos]
    names = list(pos)

    def coarse(i, bw):
        a, b = ends[i]
        c = arc(pos[a], pos[b], bw)
        return c[::5] + ([c[-1]] if len(c) % 5 != 1 else [])

    def node_hits(i, poly):
        """Nodes the curve runs through (10 each) or close past (0.6 each)."""
        a, b = ends[i]
        x0, y0, x1, y1 = _bbox(poly)
        m = need + 0.3
        near = [p for n, p in zip(names, pts) if n not in (a, b)
                and x0 - m < p[0] < x1 + m and y0 - m < p[1] < y1 + m]
        score = 0.0
        for o in near:
            c = _clearance(poly, [o])
            score += 10.0 if c < need else (0.6 if c < m else 0.0)
        return score

    bows = [0.0] * len(ends)
    polys = [coarse(i, 0.0) for i in range(len(ends))]
    boxes = [_bbox(p) for p in polys]

    def cost(i, bw):
        poly = coarse(i, bw)
        box = _bbox(poly)
        cross = 0
        for j in range(len(ends)):
            if j == i:
                continue
            shared = set(ends[j]) & set(ends[i])
            if not shared:
                cross += _n_cross(poly, box, polys[j], boxes[j])
                continue
            # edges meeting at a node: only crossings away from that node count
            pa, pb = poly, polys[j]
            for n in shared:
                cut = R + 0.25
                pa = _cut_start(pa, cut) if ends[i][0] == n else _cut_end(pa, cut)
                pb = _cut_start(pb, cut) if ends[j][0] == n else _cut_end(pb, cut)
            if len(pa) > 1 and len(pb) > 1:
                cross += _n_cross(pa, _bbox(pa), pb, _bbox(pb))
        return node_hits(i, poly) + cross + 0.8 * abs(bw), poly, box

    # long edges first, they have the most room to swing out
    order = sorted(range(len(ends)), key=lambda i: -math.hypot(
        pos[ends[i][0]][0] - pos[ends[i][1]][0], pos[ends[i][0]][1] - pos[ends[i][1]][1]))
    for _ in range(8):
        changed = False
        for i in order:
            best = min((cost(i, bw) + (bw,) for bw in BOWS), key=lambda t: t[0])
            if best[3] != bows[i]:
                bows[i], polys[i], boxes[i] = best[3], best[1], best[2]
                changed = True
        if not changed:
            break
    return bows


def _arrow(tip, prev, color, size=ARROW):
    """Arrowhead with its tip exactly at tip, pointing from prev to tip."""
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    bx, by = tip[0] - ux * size, tip[1] - uy * size
    w = size * 0.4
    return {"t": "poly", "pts": [tip, (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)],
            "fill": color, "stroke": None, "w": 0, "dash": None}


def _edge_items(pts, color, width, dash, head, tail):
    """Line along pts with arrowheads at its end (head) and/or start (tail)."""
    if len(pts) < 2:
        return []
    items = []
    line = pts
    if head:
        items.append(_arrow(pts[-1], pts[-6] if len(pts) > 6 else pts[0], color))
        line = _cut_end(line, ARROW * 0.8)
    if tail:
        items.append(_arrow(pts[0], pts[5] if len(pts) > 5 else pts[-1], color))
        line = _cut_start(line, ARROW * 0.8)
    if len(line) >= 2:
        items.insert(0, {"t": "line", "pts": line, "color": color, "w": width, "dash": dash})
    return items


# ==============================================================================
# Nodes
# ==============================================================================


def _box_size(d):
    label = str(d.get("label", ""))
    size = d.get("label_size", 0.19)
    w = d.get("width") or max(2 * R, 0.55 * size * len(label) + 0.3)
    h = d.get("height") or 0.5
    return w, h


def _outline(d):
    """How a node ends edges: ("circle", radius) or ("box", half width, half height)."""
    shape = d.get("shape", "circle")
    if shape == "box":
        w, h = _box_size(d)
        grow = d.get("stroke_width", 0.0) / 2.0 if d.get("stroke") else 0.0
        return ("box", w / 2.0 + grow, h / 2.0 + grow)
    if d.get("outline") is not None:
        return ("circle", d["outline"])
    r = d.get("radius", R)
    if shape == "octagon":
        return ("circle", r * 1.1)
    if d.get("stroke"):
        return ("circle", r + d.get("stroke_width", 0.0) / 2.0)
    return ("circle", r)


def _cut_to(pts, start, end):
    if start[0] == "box":
        pts = _cut_start_box(pts, start[1], start[2])
    else:
        pts = _cut_start(pts, start[1])
    if len(pts) < 2:
        return pts
    if end[0] == "box":
        return _cut_end_box(pts, end[1], end[2])
    return _cut_end(pts, end[1])


def _node_items(n, x, y, d):
    shape = d.get("shape", "circle")
    fill = d.get("fill", GREY)
    stroke = d.get("stroke")
    w = d.get("stroke_width", 0.0) if stroke else 0.0
    size = d.get("label_size", 0.19 if shape != "octagon" else 0.2)
    label = str(d.get("label", n))
    txt = d.get("text_color") or text_on(fill)
    tag = {"n": n}
    if d.get("fixed"):
        tag["fixed"] = True
    items = []
    if shape == "octagon":
        r = d.get("radius", R) * 1.1
        pts = [(x + r * math.cos(math.pi / 8 + i * math.pi / 4), y + r * math.sin(math.pi / 8 + i * math.pi / 4)) for i in range(8)]
        items.append(dict({"t": "poly", "pts": pts, "fill": fill, "stroke": stroke, "w": w, "dash": None}, **tag))
    elif shape == "box":
        bw, bh = _box_size(d)
        x0, x1, y0, y1 = x - bw / 2.0, x + bw / 2.0, y - bh / 2.0, y + bh / 2.0
        items.append(dict({"t": "poly", "pts": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                           "fill": fill, "stroke": stroke, "w": w, "dash": d.get("dash")}, **tag))
    else:
        items.append(dict({"t": "circle", "c": (x, y), "r": d.get("radius", R), "fill": fill, "stroke": stroke, "w": w}, **tag))
    items.append(dict({"t": "text", "s": label, "pos": (x, y), "size": size, "color": txt,
                       "anchor": "middle", "bold": d.get("bold", True)}, **tag))
    return items


# ==============================================================================
# Draw
# ==============================================================================


def draw(graph, positions, regions=None, title=None, legend=None, note=None, route=True):
    """Draw a graph whose nodes and edges carry the styling attributes.

    Parameters
    ----------
    graph : :class:`compas.datastructures.Graph`
        The graph, with the node and edge attributes listed in the module docstring.
        Edges are drawn from their first to their second node.
    positions : dict
        Position (x, y) per node key. Nodes without a position are left out.
    regions : list[dict], optional
        Dashed boxes around groups of nodes: {"name": title, "nodes": [keys]},
        with an optional "side" (x, y) that places the title on the outer corner.
    title : str, optional
        Title in the upper left corner.
    legend : list[tuple[str, str]], optional
        (colour, text) entries in a row under the drawing.
    note : str, optional
        A line of explanation under the legend.
    route : bool, optional
        Curve edges around nodes and crossings (default True). False draws them straight.

    Returns
    -------
    :class:`Drawing`

    """
    pos = dict(positions)
    items = []
    data = {n: dict(graph.node[n]) for n in graph.nodes()}

    for region in regions or []:
        pts = [pos[n] for n in region["nodes"] if n in pos]
        if not pts:
            continue
        x0 = min(p[0] for p in pts) - R - 0.45
        x1 = max(p[0] for p in pts) + R + 0.45
        y0 = min(p[1] for p in pts) - R - 0.45
        y1 = max(p[1] for p in pts) + R + 0.45
        items.append({"t": "poly", "pts": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                      "fill": None, "stroke": INK_MUTED, "w": 0.025, "dash": "dash"})
        a = region.get("side") or (0.0, 0.0)
        tx = x1 - 0.2 if a[0] > 0.5 else x0 + 0.2
        ty = y1 + 0.35 if a[1] > -0.5 else y0 - 0.35
        items.append({"t": "text", "s": region["name"], "pos": (tx, ty), "size": 0.34,
                      "color": INK, "anchor": "end" if a[0] > 0.5 else "start", "bold": False})

    # edges, drawn under the nodes
    edges = []
    for (u, v), d in graph.edges(data=True):
        if u in pos and v in pos and u in data and v in data:
            edges.append((u, v, dict(d)))
    edges.sort(key=lambda e: e[2].get("order", 0))  # stable: without "order" the graph's own order
    if route:
        bows = route_edges([(u, v) for u, v, _ in edges], {n: pos[n] for n in pos if n in data}, R + 0.12)
    else:
        bows = [0.0] * len(edges)
    for (u, v, d), bow in zip(edges, bows):
        arrow = d.get("arrow")
        pts = _cut_to(arc(pos[u], pos[v], bow), _outline(data[u]), _outline(data[v]))
        source = d.get("source")
        for it in _edge_items(pts, d.get("color", INK), d.get("width", EDGE_W), d.get("dash"),
                              head=arrow in ("head", "both"), tail=arrow == "both"):
            it["e"] = tuple(source) if source is not None else (u, v)
            items.append(it)

    # nodes
    for n in pos:
        if n in data:
            items.extend(_node_items(n, pos[n][0], pos[n][1], data[n]))

    # legend under the drawing, title above it
    b0 = bounds(items) if items else (0.0, 0.0, 1.0, 1.0)
    if legend:
        lx, ly = b0[0] + 0.3, b0[1] - 0.4
        x = lx
        for color, label in legend:
            items.append({"t": "circle", "c": (x + 0.15, ly), "r": 0.15, "fill": color, "stroke": None, "w": 0})
            items.append({"t": "text", "s": label, "pos": (x + 0.42, ly), "size": 0.22, "color": INK,
                          "anchor": "start", "bold": False})
            x += 0.42 + 0.13 * len(label) + 0.5
        if note:
            items.append({"t": "text", "s": note, "pos": (lx, ly - 0.5), "size": 0.19, "color": INK_MUTED,
                          "anchor": "start", "bold": False})
    elif note:
        items.append({"t": "text", "s": note, "pos": (b0[0] + 0.3, b0[1] - 0.4), "size": 0.19, "color": INK_MUTED,
                      "anchor": "start", "bold": False})
    if title:
        items.append({"t": "text", "s": title, "pos": (b0[0] + 0.3, b0[3] + 0.3), "size": 0.26,
                      "color": INK_MUTED, "anchor": "start", "bold": False})
    return Drawing(items, bounds(items), title)


# ==============================================================================
# Focus
# ==============================================================================


def _fade(it, f=FADE):
    out = dict(it)
    for k in ("fill", "stroke", "color"):
        if out.get(k):
            out[k] = blend(out[k], f)
    return out


def _ring(c, r, color, w):
    pts = [(c[0] + r * math.cos(2 * math.pi * i / 48), c[1] + r * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    return {"t": "poly", "pts": pts, "fill": None, "stroke": color, "w": w, "dash": None, "ring": True}


def highlight(items, focus, colors=None):
    """The items with a focus on one node.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.
    focus : dict or None
        {"roles": {node: role}, "edges": set of frozenset node pairs}, with the
        role "sel" for the node in focus. None leaves the items as they are.
    colors : dict, optional
        Ring colour per role.

    Returns
    -------
    list[dict]
        The first len(items) entries correspond one to one to items (only
        colours change): nodes with a role and the edges of the focus keep
        their colours, everything else fades. Rings in the role colours follow.

    """
    if not focus:
        return list(items)
    colors = colors or {}
    roles, edges = focus["roles"], focus["edges"]
    out, rings = [], []
    for it in items:
        n, e = it.get("n"), it.get("e")
        if n is not None:
            if it.get("fixed") or n in roles:
                out.append(it)
                if it["t"] == "circle" and n in roles:
                    role = roles[n]
                    color = colors.get(role, INK)
                    if role == "sel":
                        rings.append(_ring(it["c"], it["r"] + 0.13, color, 0.08))
                    else:
                        rings.append(_ring(it["c"], it["r"] + 0.11, color, 0.05))
            else:
                out.append(_fade(it))
        elif e is not None:
            out.append(it if frozenset(e) in edges else _fade(it, 0.86))
        else:
            out.append(it)
    return out + rings


def node_positions(items):
    """Positions of the circle nodes of a drawing. Fixed nodes are left out.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.

    Returns
    -------
    dict
        ``{node: (x, y, r)}``.

    """
    return {it["n"]: (it["c"][0], it["c"][1], it["r"]) for it in items
            if it["t"] == "circle" and it.get("n") is not None and not it.get("fixed")}


def pick(items, x, y, slack=0.08):
    """The node under a point of the drawing.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.
    x : float
        X of the point, in drawing units.
    y : float
        Y of the point, in drawing units.
    slack : float, optional
        How far outside a node a point still counts, in drawing units.

    Returns
    -------
    hashable | None
        The node key, or None if no node is there.

    """
    best = None
    for n, (cx, cy, r) in node_positions(items).items():
        d = math.hypot(x - cx, y - cy)
        if d <= r + slack and (best is None or d < best[0]):
            best = (d, n)
    return best[1] if best else None


def bounds(items):
    """The box around the items, with a small margin.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.

    Returns
    -------
    tuple[float, float, float, float]
        ``(x0, y0, x1, y1)``.

    """
    xs, ys = [], []
    for it in items:
        if it["t"] == "circle":
            xs += [it["c"][0] - it["r"], it["c"][0] + it["r"]]
            ys += [it["c"][1] - it["r"], it["c"][1] + it["r"]]
        elif it["t"] == "text":
            x, y = it["pos"]
            w = 0.55 * it["size"] * len(it["s"])
            anchor = it.get("anchor", "middle")
            xs += [x, x + w] if anchor == "start" else ([x - w, x] if anchor == "end" else [x - w / 2, x + w / 2])
            ys += [y - it["size"], y + it["size"]]
        else:
            xs += [p[0] for p in it["pts"]]
            ys += [p[1] for p in it["pts"]]
    pad = 0.3
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


_items_bounds = bounds  # for Drawing, whose bounds argument hides the function

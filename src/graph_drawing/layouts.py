"""
Layouts: positions for the nodes of a graph, in drawing units (y up).

support
    The support hierarchy drawing of Bruun et al. 2024 (Construction
    Robotics 8:20, Fig. 7) for frames: every wall gets a region, the members
    stand in columns by their place in the load path, ground outside.
layered
    For directed acyclic graphs such as action graphs and programs of interventions:
    steps in layers along the direction of the edges, ordered within a layer
    so that edges cross as little as possible.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

__all__ = ["support", "layered", "layers"]


R = 0.30      # node radius
DX = 1.75     # column spacing
DY = 1.00     # row spacing
GAP = 0.90    # smallest distance between two nodes of a column

# Columns of a wall region, from the outside (ground) inwards, by member type.
# Rails and top beams share the inner column: both rest on the posts, so all
# edges of a wall run between neighbouring columns. support() splits the rail
# column further by height and puts the top beams after it.
COLUMNS = [("sill",), ("post", "brace", "strut"), ("rail", "top")]


# ==============================================================================
# Support
# ==============================================================================


def _column_of(t):
    for i, ts in enumerate(COLUMNS):
        if t in ts:
            return i + 1
    return len(COLUMNS) + 1  # anything else inside the wall: innermost


def support(graph):
    """Positions in the manner of a plan seen from above, and the wall regions.

    Every wall gets a region on the side its outward normal points to (south
    wall below, west wall left, ...). Inside a region the members stand in
    columns by type, ground outside, and within a column in their order along
    the wall. Members of two walls stand in the corner between the two
    regions; members of no wall (joists, ...) in the middle.

    Parameters
    ----------
    graph : :class:`compas.datastructures.Graph`
        A graph as made by :func:`graph_drawing.frames.drawing_graph`: the
        graph attribute "walls" lists the walls (name, normal, along), every
        member node has "type", "walls", "wall_u" and "center", and one node
        per wall with the attribute "ground" (the wall's name) stands for the
        ground under it.

    Returns
    -------
    tuple[dict, list[dict]]
        Position (x, y) per node, and one region per wall:
        {"name": "Front wall", "wall": name, "side": outward normal in the drawing, "nodes": [keys]}.

    """
    nodes = {n: graph.node[n] for n in graph.nodes()}
    walls = {w["name"]: w for w in graph.attributes.get("walls", [])}
    grounds = {d["ground"]: n for n, d in nodes.items() if d.get("ground")}
    parts = [n for n, d in nodes.items() if not d.get("ground")]
    single = {w: [n for n in parts if nodes[n].get("walls") == [w]] for w in walls}
    single = {w: ns for w, ns in single.items() if ns}
    corner = [n for n in parts if len(nodes[n].get("walls", [])) > 1]
    middle = [n for n in parts if not nodes[n].get("walls")]

    # columns per wall, inner offset large enough that neighbouring regions never touch
    cols, nbands = {}, {}
    for w, ns in single.items():
        # rails get one column per height level (lower rails nearer the posts), so
        # that every rail can stand above its own bay; top beams come after them
        zs = sorted(nodes[n]["center"][2] for n in ns if nodes[n].get("type") == "rail")
        bands = []
        for z in zs:
            if not bands or z - bands[-1][-1] > 0.25:
                bands.append([z])
            else:
                bands[-1].append(z)

        def band(z):
            return min(range(len(bands)), key=lambda i: abs(z - sum(bands[i]) / len(bands[i])))
        c = {}
        for n in ns:
            typ = nodes[n].get("type")
            if typ == "rail":
                ci = 3 + band(nodes[n]["center"][2])
            elif typ == "top":
                ci = 3 + len(bands)
            elif typ in ("sill", "post", "brace", "strut"):
                ci = _column_of(typ)
            else:
                ci = 4 + len(bands)
            c.setdefault(ci, []).append(n)
        cols[w] = c
        nbands[w] = len(bands)
    max_rows = max([len(ns) for c in cols.values() for ns in c.values()] + [1])
    inner = (max_rows - 1) / 2.0 * DY + R + 0.9 * DX
    if middle:
        inner = max(inner, (len(middle) - 1) / 2.0 * DY + R + 1.2 * DX)

    pos, regions = {}, []
    for w, c in cols.items():
        nb = nbands[w]
        nrm = walls[w]["normal"]
        a = (nrm[0], nrm[1])                  # outward, in the drawing
        t = (-a[1], a[0])                     # along the wall
        along = walls[w]["along"]
        used = sorted(c)
        sgn = along[0] * t[0] + along[1] * t[1]

        def key(n):
            return nodes[n]["wall_u"].get(w, 0.0) * sgn

        # reference column (posts if present): evenly spaced in wall order
        ref_ci = 2 if 2 in c else max(c, key=lambda ci: len(c[ci]))
        ref = sorted(c[ref_ci], key=lambda n: (key(n), -nodes[n]["center"][2]))
        ref_u = [key(n) for n in ref]
        ref_r = [(j - (len(ref) - 1) / 2.0) * DY for j in range(len(ref))]

        def interp(u):
            """Drawing coordinate of wall position u, between the reference members."""
            if len(ref_u) < 2 or ref_u[-1] - ref_u[0] < 1e-9:
                return 0.0
            if u <= ref_u[0]:
                return ref_r[0] + (u - ref_u[0]) / (ref_u[1] - ref_u[0] + 1e-9) * DY
            if u >= ref_u[-1]:
                return ref_r[-1] + (u - ref_u[-1]) / (ref_u[-1] - ref_u[-2] + 1e-9) * DY
            for i in range(1, len(ref_u)):
                if u <= ref_u[i]:
                    f = (u - ref_u[i - 1]) / (ref_u[i] - ref_u[i - 1] + 1e-9)
                    return ref_r[i - 1] + f * (ref_r[i] - ref_r[i - 1])
            return ref_r[-1]

        for k, ci in enumerate(reversed(used)):  # innermost column first
            ns = sorted(c[ci], key=lambda n: (key(n), -nodes[n]["center"][2]))
            if ci == ref_ci:
                rs = list(ref_r)
            else:
                # each member sits where it is along the wall, relative to the posts,
                # pushed apart just enough that nodes do not overlap
                want = [interp(key(n)) for n in ns]
                rs = []
                for x in want:
                    rs.append(x if not rs else max(x, rs[-1] + GAP))
                shift = (sum(want) - sum(rs)) / len(rs)
                rs = [r + shift for r in rs]
                for i in range(len(rs) - 2, -1, -1):  # keep the gap after the shift
                    rs[i] = min(rs[i], rs[i + 1] - GAP)
            if ci > 3 and ci < 3 + nb:  # upper rail bands slightly staggered,
                rs = [r + 0.22 * DY * ((ci - 3) % 2) for r in rs]  # so their edges do not run over the lower rails
            dist = inner + k * DX
            for n, r in zip(ns, rs):
                pos[n] = (a[0] * dist + t[0] * r, a[1] * dist + t[1] * r)
        g = grounds.get(w)
        region = list(single[w])
        if g is not None:
            dist = inner + len(used) * DX
            pos[g] = (a[0] * dist, a[1] * dist)
            region.append(g)
        regions.append({"name": "%s wall" % w.capitalize(), "wall": w, "side": a, "nodes": region})

    # corners: between the two regions they belong to
    groups = {}
    for n in corner:
        groups.setdefault(tuple(sorted(nodes[n]["walls"])), []).append(n)
    for key, ns in groups.items():
        dirs = [walls[w]["normal"] for w in key if w in walls]
        cx = sum(d[0] for d in dirs)
        cy = sum(d[1] for d in dirs)
        L = math.hypot(cx, cy) or 1.0
        cx, cy = cx / L, cy / L
        dist = inner * math.sqrt(2.0) * 0.85
        tx, ty = -cy, cx
        ns.sort(key=lambda n: -nodes[n]["center"][2])
        for j, n in enumerate(ns):
            r = (j - (len(ns) - 1) / 2.0) * DY
            pos[n] = (cx * dist + tx * r, cy * dist + ty * r)

    # middle: members of no wall, spread along their main direction in plan
    if middle:
        xs = [nodes[n]["center"][0] for n in middle]
        ys = [nodes[n]["center"][1] for n in middle]
        horiz = (max(xs) - min(xs)) >= (max(ys) - min(ys))
        middle.sort(key=lambda n: nodes[n]["center"][0] if horiz else nodes[n]["center"][1])
        for j, n in enumerate(middle):
            r = (j - (len(middle) - 1) / 2.0) * DY * 1.4
            pos[n] = (r, 0.0) if horiz else (0.0, r)
    return pos, regions


# ==============================================================================
# Layered
# ==============================================================================


def layers(graph):
    """Layer of every node: the length of the longest path of edges ending in it.

    Edges that close a cycle are left out (the first edge found that leads
    back to a node on the current path), so the result is defined for any
    directed graph.

    Parameters
    ----------
    graph : :class:`compas.datastructures.Graph`
        A directed graph.

    Returns
    -------
    dict
        Layer index per node key, starting at 0.

    """
    keys = list(graph.nodes())
    out = {n: [] for n in keys}
    for (u, v) in graph.edges():
        if u != v:
            out[u].append(v)
    # depth first: drop edges back onto the current path
    state, keep = {}, {n: [] for n in keys}
    for root in keys:
        if root in state:
            continue
        stack = [(root, iter(out[root]))]
        state[root] = 1
        while stack:
            n, it = stack[-1]
            for m in it:
                if state.get(m) == 1:
                    continue  # back edge
                keep[n].append(m)
                if m not in state:
                    state[m] = 1
                    stack.append((m, iter(out[m])))
                break
            else:
                state[n] = 2
                stack.pop()
    indeg = {n: 0 for n in keys}
    for n in keys:
        for m in keep[n]:
            indeg[m] += 1
    layer = {n: 0 for n in keys}
    ready = [n for n in keys if indeg[n] == 0]
    while ready:
        n = ready.pop(0)
        for m in keep[n]:
            layer[m] = max(layer[m], layer[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    return layer


def layered(graph, direction="down", spacing=0.6, gap=0.35, sweeps=4):
    """Positions for a directed graph in layers along its edges.

    Parameters
    ----------
    graph : :class:`compas.datastructures.Graph`
        The graph. Edges point from earlier to later steps.
    direction : {"down", "right"}, optional
        Where the edges point: "down" puts the first layer on top,
        "right" puts it on the left.
    spacing : float, optional
        Free space between two layers.
    gap : float, optional
        Free space between two nodes of a layer.
    sweeps : int, optional
        Rounds of reordering within the layers (barycentres of the neighbours).

    Returns
    -------
    tuple[dict, list]
        Position (x, y) per node and an empty list of regions.

    """
    from .drawing import _box_size

    layer = layers(graph)
    rows = {}
    for n in graph.nodes():  # insertion order is the first order within a layer
        rows.setdefault(layer[n], []).append(n)
    order = [rows[i] for i in sorted(rows)]
    preds = {n: [] for n in graph.nodes()}
    succs = {n: [] for n in graph.nodes()}
    for (u, v) in graph.edges():
        preds[v].append(u)
        succs[u].append(v)

    def size(n):
        """Extent of a node across its layer and along the direction."""
        d = graph.node[n]
        if d.get("shape") == "box":
            w, h = _box_size(d)
        else:
            w = h = 2 * d.get("radius", R)
        return (w, h) if direction == "down" else (h, w)

    def place(row):
        """Coordinates across the layer, centred on 0."""
        widths = [size(n)[0] for n in row]
        total = sum(widths) + gap * (len(row) - 1)
        x, out = -total / 2.0, {}
        for n, w in zip(row, widths):
            out[n] = x + w / 2.0
            x += w + gap
        return out

    for s in range(sweeps):
        down = s % 2 == 0
        idx = range(1, len(order)) if down else range(len(order) - 2, -1, -1)
        for i in idx:
            ref = place(order[i - 1] if down else order[i + 1])
            cur = place(order[i])

            def bary(n):
                nbrs = [m for m in (preds[n] if down else succs[n]) if m in ref]
                return sum(ref[m] for m in nbrs) / len(nbrs) if nbrs else cur[n]
            order[i] = sorted(order[i], key=lambda n: (bary(n), cur[n]))

    pos = {}
    along, prev = 0.0, None
    for row in order:
        depth = max(size(n)[1] for n in row)
        if prev is not None:
            along += (prev + depth) / 2.0 + spacing
        prev = depth
        across = place(row)
        for n in row:
            pos[n] = (across[n], -along) if direction == "down" else (along, -across[n])
    return pos, []

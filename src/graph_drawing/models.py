"""
Graphs of models and of steps, styled for drawing.

from_model reads a compas_model ``Model`` whose graph carries the state of an
intervention in the convention shared with intervention_grammar (graph_drawing
does not import intervention_grammar; the convention is only a set of
attribute names):

Node attributes, per element node of ``model.graph``
    fabric      "original" | "new"
    condition   "sound" | "damaged"
    placement   "in" | "inserted" | "out" | "missing"
    type        the role of the element, any name (optional)
    grounded    True for elements standing on the ground

Edge attributes, per connection
    joint       a joint description (dict or str)
    state       "secured" | "released" | "open"
    at          {element name: station along that element}
    support     (carried name, carrier name) or "both" (optional)

steps draws any sequence or directed graph of labelled steps, such as a program
of interventions or a plan of actions.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from compas.datastructures import Graph

from . import layouts
from .drawing import INK
from .drawing import INK_MUTED
from .drawing import draw
from .frames import DEFECT
from .frames import MISSING_TAG
from .frames import TYPE
from .frames import TYPE_ORDER

__all__ = ["from_model", "drawing", "steps"]

GROUND = "ground"


# ==============================================================================
# Models
# ==============================================================================


def _type_colors(types):
    """A colour per element type: the colours of :mod:`graph_drawing.frames` for the
    member types it knows, the remaining palette colours in order for all others."""
    palette = [TYPE[t]["color"] for t in TYPE_ORDER if t != "other"]
    known = {t: TYPE[t]["color"] for t in types if t in TYPE and t != "other"}
    free = [c for c in palette if c not in known.values()]
    colors = {}
    for t in types:
        if t in known:
            colors[t] = known[t]
        elif t is None or t == "other" or not free:
            colors[t] = TYPE["other"]["color"]
        else:
            colors[t] = free.pop(0)
    return colors


def _style(d, color):
    """Fill, ring and text of an element node from its state."""
    style = {"fill": color, "stroke": None, "stroke_width": 0.0, "text_color": None, "dash": None}
    placement = d.get("placement", "in")
    if placement == "missing":
        style.update(fill=MISSING_TAG, stroke=color, stroke_width=0.04, text_color=INK)
    elif placement == "out":
        style.update(fill="#ffffff", stroke=color, stroke_width=0.04, text_color=INK, dash="dash")
    if d.get("fabric") == "new":
        style.update(stroke=INK, stroke_width=0.06)
    if d.get("condition") == "damaged":
        style.update(stroke=DEFECT, stroke_width=0.09)
    return style


def from_model(model):
    """A styled graph of a compas_model model and its state.

    Parameters
    ----------
    model : :class:`compas_model.models.Model`
        The model. Its graph carries the attributes listed in the module docstring.

    Returns
    -------
    :class:`compas.datastructures.Graph`
        One box per element, labelled with its name and coloured by type; a red
        ring for damaged elements, a black ring for new ones, yellow for
        missing ones, white with a dashed outline for elements taken out.
        Connections with a support direction point from the carried element
        to the carrying one; released connections are dashed, open ones
        dotted. Grounded elements point to one ground node.

    """
    G = model.graph
    g = Graph(name=model.name or "model")
    name = {}
    grounded = []
    types = []
    for node in G.nodes():
        t = G.node[node].get("type") or "other"
        if t not in types:
            types.append(t)
    colors = _type_colors(types)
    for node in G.nodes():
        element = G.node_element(node)
        key = element.name if element is not None else str(node)
        name[node] = key
        d = G.node[node]
        style = _style(d, colors[d.get("type") or "other"])
        g.add_node(key, label=key, shape="box", bold=False, type=d.get("type") or "other", type_color=colors[d.get("type") or "other"],
                   fabric=d.get("fabric", "original"), condition=d.get("condition", "sound"),
                   placement=d.get("placement", "in"), **style)
        if d.get("grounded"):
            grounded.append(key)
    for i, (u, v) in enumerate(G.edges()):
        d = G.edge[u][v]
        a, b = name[u], name[v]
        s = d.get("support")
        arrow = None
        if isinstance(s, (list, tuple)) and len(s) == 2:
            a, b = s[0], s[1]
            arrow = "head"
        elif s == "both":
            arrow = "both"
        color = g.node[a].get("type_color", INK_MUTED) if arrow == "head" else INK_MUTED
        dash = {"released": "dash", "open": "dot"}.get(d.get("state"))
        g.add_edge(a, b, color=color, dash=dash, arrow=arrow, source=(name[u], name[v]), order=i,
                   joint=d.get("joint"), state=d.get("state", "secured"))
    if grounded:
        g.add_node(GROUND, label="G", shape="octagon", fill="#000000", fixed=True)
        for k in grounded:
            g.add_edge(k, GROUND, color=g.node[k]["type_color"], arrow="head",
                       source=(k, GROUND), order=len(name) + len(grounded))
    return g


def drawing(model, title=None, direction="down"):
    """Draw a compas_model model with :func:`from_model` and the layered layout.

    Parameters
    ----------
    model : :class:`compas_model.models.Model`
        The model.
    title : str, optional
        Title of the drawing. Defaults to the model's name.
    direction : {"down", "right"}, optional
        Direction of the support arrows in the layout.

    Returns
    -------
    :class:`graph_drawing.drawing.Drawing`

    """
    g = from_model(model)
    pos, regions = layouts.layered(g, direction=direction)
    entries = []
    for n in g.nodes():
        d = g.node[n]
        if n != GROUND and (d["type_color"], d["type"]) not in entries:
            entries.append((d["type_color"], d["type"]))
    note = ("arrow: rests on    red ring: damaged    black ring: new    yellow: missing    "
            "white: taken out    dashed: released    dotted: open")
    return draw(g, pos, regions, title=title or model.name, legend=entries, note=note)


# ==============================================================================
# Steps
# ==============================================================================


def steps(labels, edges=None, fills=None):
    """A graph of labelled steps, ready for :func:`graph_drawing.layouts.layered`.

    Parameters
    ----------
    labels : list[str] or dict
        The label of every step, as a list (keys 0, 1, 2, ...) or as a dict {key: label}.
    edges : list[tuple], optional
        (before, after) pairs of keys. Defaults to a chain in the given order.
    fills : dict, optional
        Fill colour per key (default white).

    Returns
    -------
    :class:`compas.datastructures.Graph`

    Examples
    --------
    >>> from graph_drawing import steps, layouts, draw
    >>> g = steps(["Release pegs", "Withdraw post", "Insert new post", "Secure"])
    >>> pos, regions = layouts.layered(g)
    >>> d = draw(g, pos, regions)

    """
    if not isinstance(labels, dict):
        labels = dict(enumerate(labels))
    keys = list(labels)
    if edges is None:
        edges = list(zip(keys, keys[1:]))
    fills = fills or {}
    g = Graph(name="steps")
    for k in keys:
        g.add_node(k, label=str(labels[k]), shape="box", fill=fills.get(k, "#ffffff"), stroke=INK,
                   stroke_width=0.025, text_color=INK, bold=False)
    for i, (u, v) in enumerate(edges):
        g.add_edge(u, v, color=INK_MUTED, arrow="head", order=i)
    return g

import pytest

from graph_drawing import from_model
from graph_drawing import models

compas_model = pytest.importorskip("compas_model")


def wall():
    from compas_model.elements import Element
    from compas_model.models import Model

    model = Model(name="wall")
    els = {}
    for name, typ in [("sill", "sill"), ("post_1", "post"), ("post_2", "post"), ("rail", "rail"), ("plate", "top")]:
        els[name] = Element(name=name)
        model.add_element(els[name])
        model.graph.node_attribute(els[name].graphnode, "type", typ)
    G = model.graph

    def connect(a, b, carried, carrier, state="secured"):
        model.add_interaction(els[a], els[b])
        edge = (els[a].graphnode, els[b].graphnode)
        G.edge_attribute(edge, "joint", "tenon")
        G.edge_attribute(edge, "state", state)
        G.edge_attribute(edge, "support", (carried, carrier))

    connect("post_1", "sill", "post_1", "sill")
    connect("post_2", "sill", "post_2", "sill", state="released")
    connect("rail", "post_1", "rail", "post_1")
    connect("rail", "post_2", "rail", "post_2")
    connect("plate", "post_1", "plate", "post_1")
    connect("plate", "post_2", "plate", "post_2")
    G.node_attribute(els["sill"].graphnode, "grounded", True)
    G.node_attribute(els["post_2"].graphnode, "condition", "damaged")
    G.node_attribute(els["rail"].graphnode, "fabric", "new")
    G.node_attribute(els["plate"].graphnode, "placement", "out")
    return model


def test_from_model_styles():
    g = from_model(wall())
    assert set(g.nodes()) == {"sill", "post_1", "post_2", "rail", "plate", "ground"}
    assert g.node["post_2"]["stroke"] == "#c0392b"  # damaged: red ring
    assert g.node["rail"]["stroke"] == "#0b0b0b"    # new: black ring
    assert g.node["plate"]["fill"] == "#ffffff"     # taken out: hollow
    assert g.has_edge(("post_1", "sill")) and g.has_edge(("sill", "ground"))
    released = [d for (u, v), d in g.edges(data=True) if (u, v) == ("post_2", "sill")][0]
    assert released["dash"] == "dash"


def test_model_drawing_layers():
    d = models.drawing(wall())
    pos = {it["n"]: it["pts"] for it in d.items if it["t"] == "poly" and it.get("n") in ("plate", "sill")}
    top = max(p[1] for p in pos["plate"])
    bottom = max(p[1] for p in pos["sill"])
    assert top > bottom  # the plate rests on the posts, which rest on the sill

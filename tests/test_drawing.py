import compas
from compas.datastructures import Graph

from graph_drawing import Drawing
from graph_drawing import draw
from graph_drawing import layouts
from graph_drawing import steps


def dag():
    g = Graph()
    for k in "abcde":
        g.add_node(k, label=k.upper())
    for u, v in [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e"), ("a", "e")]:
        g.add_edge(u, v, arrow="head")
    return g


def test_layers():
    assert layouts.layers(dag()) == {"a": 0, "b": 1, "c": 1, "d": 2, "e": 3}


def test_layers_with_cycle():
    g = dag()
    g.add_edge("e", "a")  # closes a cycle, left out
    assert layouts.layers(g)["e"] == 3


def test_layered_positions():
    pos, regions = layouts.layered(dag())
    assert regions == []
    assert pos["a"][1] > pos["b"][1] > pos["d"][1] > pos["e"][1]
    assert abs(pos["b"][1] - pos["c"][1]) < 1e-9
    assert pos["b"][0] != pos["c"][0]
    right, _ = layouts.layered(dag(), direction="right")
    assert right["a"][0] < right["b"][0] < right["d"][0] < right["e"][0]


def test_draw_items():
    g = dag()
    pos, regions = layouts.layered(g)
    d = draw(g, pos, regions, title="dag", legend=[("#2a78d6", "S Sill")], note="a note")
    circles = [it for it in d.items if it["t"] == "circle" and it.get("n")]
    assert len(circles) == 5
    arrows = [it for it in d.items if it["t"] == "poly" and it.get("e")]
    assert len(arrows) == 6
    assert d.pick(pos["c"][0], pos["c"][1]) == "c"


def test_steps_boxes():
    g = steps(["Release pegs", "Withdraw post", "Insert new post", "Secure"])
    pos, _ = layouts.layered(g)
    d = draw(g, pos)
    boxes = [it for it in d.items if it["t"] == "poly" and it.get("n") is not None]
    assert len(boxes) == 4
    lines = [it for it in d.items if it["t"] == "line"]
    # every edge ends on the box outline, so it runs between the boxes only
    for line in lines:
        assert min(p[1] for p in line["pts"]) > min(pos.values(), key=lambda p: p[1])[1] - 0.3


def test_drawing_json_roundtrip():
    g = dag()
    pos, _ = layouts.layered(g)
    d = draw(g, pos, title="dag")
    e = compas.json_loads(compas.json_dumps(d))
    assert isinstance(e, Drawing)
    assert e.title == "dag"
    assert len(e.items) == len(d.items)
    assert e.to_svg() == d.to_svg()

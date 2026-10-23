import os

import pytest

from graph_drawing import frames

HERE = os.path.dirname(os.path.abspath(__file__))
CORNER = os.path.join(HERE, "..", "data", "timber_corner_structure.json")


@pytest.fixture(scope="module")
def graph():
    return frames.build_graph(frames.load_parts(CORNER))


def test_parts_and_codes():
    parts = frames.load_parts(CORNER)
    assert len(parts) == 24
    codes = {p.id: p.code for p in parts}
    assert codes["top_beam_side"] == "ST"
    assert codes["middle_post_front"] == "FP1"
    assert codes["corner_post_front_left"] == "CP"


def test_report(graph):
    lines = frames.report(graph).splitlines()
    assert lines[0] == "parts: 24   connections: 46   (both 41, geometric 5)"
    assert lines[1] == "status: defective 1, intact 21, missing 2"
    assert "new parts: FD" in lines
    assert "on the ground: FS, SS" in lines
    assert "no listed connection: ST (top_beam_side)" in lines
    weak = [ln for ln in lines if ln.startswith("only edge or point contact")][0]
    assert "FR1 (upper_rail_front_left_outer) - SR6 (upper_rail_side_front_outer)" in weak
    assert "FR2 (lower_rail_front_left_outer) - SR5 (lower_rail_side_front_outer)" in weak
    assert len(graph.attributes["weak_contacts"]) == 2


def test_support_directions(graph):
    s = frames.edge_data(graph, "middle_post_front", "bottom_beam_front")["support"]
    assert tuple(s) == ("middle_post_front", "bottom_beam_front")
    d = frames.support_graph(graph)
    assert d.has_edge(("middle_post_front", "bottom_beam_front"))
    assert not d.has_edge(("bottom_beam_front", "middle_post_front"))


def test_focus(graph):
    sel = frames.find_node(graph, "fp1")
    assert sel == "middle_post_front"
    f = frames.focus(graph, sel, chain=True)
    assert f["roles"]["bottom_beam_front"] == "below"
    assert f["roles"]["top_beam_front"] == "above"
    lines = dict((role, text) for role, text in frames.focus_lines(graph, f) if role)
    assert lines["below"] == "rests on: FS"
    assert lines["above"] == "carries: FD, FR3, FR4, FR5, FR6, FT"


def test_drawing(tmp_path):
    d = frames.drawing(CORNER)
    assert d.title == "timber_corner_structure"
    assert len(d.items) == 166
    texts = [it["s"] for it in d.items if it["t"] == "text"]
    assert "Front wall" in texts and "Side wall" in texts
    grounds = [it for it in d.items if it["t"] == "poly" and len(it["pts"]) == 3 and it["fill"] == "#000000"]
    assert len(grounds) == 2
    svg = d.to_svg()
    assert svg.startswith("<svg") and "Times New Roman" in svg
    pdf = d.to_pdf(str(tmp_path / "corner.pdf"))
    with open(pdf, "rb") as f:
        assert f.read(8) == b"%PDF-1.4"


def test_highlight_keeps_items(graph):
    items, bnd = frames.scene(graph)
    f = frames.focus(graph, "middle_post_front")
    h = frames.highlight(items, f)
    assert len(h) > len(items)  # rings follow
    assert [it["t"] for it in h[:len(items)]] == [it["t"] for it in items]

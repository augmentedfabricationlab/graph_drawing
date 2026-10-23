"""
Grasshopper body of the graph_drawing component (Rhino 8, Python 3).
Executed by the loader stub in rhino/stub.py, so the component inputs are
available as globals and the outputs are read back from globals.
Inputs and outputs are created automatically from INPUTS / OUTPUTS below
(see gh_params.py), together with Custom Preview components for the coloured
geometry.

What it shows
    model         the parts as boxes, coloured by state
    tags          a dot with the short code on every part, in the colour of its
                  node in the diagram (drawn by the component itself, see below)
    model_graph   the connections on the model, centre - contact - centre
    diagram       the support graph as a schematic drawing (graph_drawing.frames),
                  lying flat next to the model
    canvas        the same drawing on the Grasshopper canvas, drawn as vector
                  graphics, so it stays sharp at any zoom

Focus on one part
    Click a part, its tag or its node in the diagram (in a Rhino viewport) or a
    node in the canvas drawing. The part, what it rests on and what rests on
    it (directly and further up the load path) keep their colours and get a
    role colour, everything else fades; a panel in the viewport and under the
    canvas drawing lists them. Click the same part again, or empty space in the
    canvas drawing, to clear. `select` sets the focus from Grasshopper.

The tags, the outlines of missing parts, the focus lines and the panel are
drawn by display handlers that this component installs (one set per
component, kept in scriptcontext.sticky and replaced on every run; they remove
themselves when the component is deleted). They follow the component's
preview switch.
"""

import importlib
import os
import sys

import Rhino
import Rhino.Geometry as rg
import System
import System.Drawing as sd
from Rhino import RhinoDoc, RhinoMath, UnitSystem

_code_dir = globals().get("RHINO_DIR")
if not _code_dir:
    raise RuntimeError("RHINO_DIR not set: run this file through the loader stub (see README.rst)")
if _code_dir not in sys.path:
    sys.path.insert(0, _code_dir)
import gh_params  # noqa: E402
import graph_drawing  # noqa: E402
import graph_drawing.drawing  # noqa: E402
import graph_drawing.export  # noqa: E402
import graph_drawing.frames  # noqa: E402
import graph_drawing.layouts  # noqa: E402
import graph_drawing.rhino.conversion  # noqa: E402

# pick up edits of the package without restarting Rhino, dependencies first
for _m in (graph_drawing.drawing, graph_drawing.layouts, graph_drawing.export, graph_drawing.frames,
           graph_drawing.rhino.conversion):
    importlib.reload(_m)
importlib.reload(gh_params)
# gh_interact is never reloaded (it defines a .NET type, see there)

from graph_drawing import drawing as gd  # noqa: E402
from graph_drawing import export  # noqa: E402
from graph_drawing import frames as ag  # noqa: E402
from graph_drawing.rhino.conversion import RhinoDrawing as _RhinoDiagram  # noqa: E402
from graph_drawing.rhino.conversion import color as _color  # noqa: E402

INPUTS = [
    ("json_path", "Path to the JSON of the frame (schema 2.1.0)", False),
    ("show_geometric", "Also show contacts the JSON does not list (default True)", True),
    ("graph_origin", "Lower left corner of the diagram, lying in the XY plane (default: right of the model)", True),
    ("graph_scale", "Size of one diagram unit in metres (default 0.2; a node is 0.3 units)", True),
    ("show_on_canvas", "Draw the diagram on the canvas below this component (default True)", True),
    ("canvas_width", "Width of the canvas drawing (default 900)", True),
    ("export", "Write the diagram as PDF and SVG into a Graph folder next to the .gh file", True),
    ("select", "Code or id of a part to focus on; takes effect when it changes, clicks work as well", True),
    ("interactive", "Click parts, tags and nodes to focus on them (default True)", True),
    ("graph_style", "Connections on the model: 0 joint (centre - joint - centre, default), "
                    "1 liaison (centre - centre), 2 frame (joints as nodes, members as bars between them)", True),
    ("chain", "Also mark the parts that lose all support from below once the selected one is out (default False)", True),
]
# (name, description, preview by the component itself)
OUTPUTS = [
    ("model", "Parts as boxes", False),
    ("model_colors", "Colour per part (state, or role when a part is in focus)", False),
    ("model_tags", "TextDot with the code of every part (the coloured tags are drawn by the component)", False),
    ("model_graph", "Connections on the model: centre - contact - centre", False),
    ("model_graph_colors", "Colour per connection (type of the carried part)", False),
    ("diagram", "Support graph as a schematic drawing (meshes and text surfaces)", False),
    ("diagram_colors", "Colour per diagram item", False),
    ("graph", "COMPAS Graph of the contacts (all attributes)", False),
    ("support", "COMPAS Graph of the support relations: u -> v means u rests on v", False),
    ("report", "Consistency check between JSON and geometry", False),
    ("legend", "Code -> part id", False),
    ("pdf", "Path of the exported PDF", False),
    ("svg", "Path of the exported SVG", False),
    ("selected", "Id of the part in focus", False),
    ("affected", "Ids of the parts that lose all support from below once it is taken out", False),
    ("selection", "The focus as text", False),
]
PREVIEWS = [("model", "model_colors"), ("model_graph", "model_graph_colors"), ("diagram", "diagram_colors")]

_ready = gh_params.ensure_params(ghenv.Component, INPUTS, OUTPUTS, PREVIEWS)  # noqa: F821

_comp = ghenv.Component  # noqa: F821
_guid = str(_comp.InstanceGuid)
KEY_UI = "graph_drawing_ui_" + _guid
KEY_CACHE = "graph_drawing_cache_" + _guid
KEY_SEL = "graph_drawing_sel_" + _guid
KEY_SEL_IN = "graph_drawing_sel_in_" + _guid


# ---------------------------------------------------------------------------
# helpers

def _pt(p, s):
    return rg.Point3d(p[0] * s, p[1] * s, p[2] * s)


def _vec(v):
    return rg.Vector3d(v[0], v[1], v[2])


def _rbox(part, s):
    plane = rg.Plane(_pt(part.center, s), _vec(part.axes[0]), _vec(part.axes[1]))
    w, h, d = (x * s for x in part.half)
    return rg.Box(plane, rg.Interval(-w, w), rg.Interval(-h, h), rg.Interval(-d, d))


# ---------------------------------------------------------------------------
# build (cached: the layout takes a second or two, a click should not)

def _mtime(p):
    try:
        return os.path.getmtime(p)
    except Exception:
        return 0.0


def _build(path, geo_flag, s, unit, origin):
    parts = ag.load_parts(path)
    graph = ag.build_graph(parts, geometric_edges=geo_flag)
    byid = {p.id: p for p in parts}
    ids = [p.id for p in parts]
    name = os.path.splitext(os.path.basename(path))[0]
    boxes = [_rbox(byid[n], s) for n in ids]

    model_edges = []  # (u, v, polyline, hex colour, contact point)
    for u, v, d in ag.edges(graph):
        if ag.GROUND in (u, v) or d.get("contact") is None:
            continue
        a, b = byid[u].center, byid[v].center
        model_edges.append((u, v, [_pt(a, s), _pt(d["contact"], s), _pt(b, s)],
                            ag.edge_color(graph, u, v, d), _pt(d["contact"], s)))

    # bar-node model: the joints are the nodes, every member a chain of bars from joint to joint
    joints = {}
    for u, v, d in ag.edges(graph):
        if ag.GROUND in (u, v) or d.get("contact") is None:
            continue
        for n in (u, v):
            joints.setdefault(n, []).append(d["contact"])
    frame = []  # (part id, [p0, p1], hex colour)
    for n in ids:
        cs = sorted(joints.get(n, []), key=byid[n].axial)
        if len(cs) == 1:
            cs.append(byid[n].center)
        for a, b in zip(cs, cs[1:]):
            if sum((a[k] - b[k]) ** 2 for k in range(3)) > 1e-6:
                frame.append((n, [_pt(a, s), _pt(b, s)], byid[n].color))

    items, bnd = ag.scene(graph, name)
    bb = rg.BoundingBox.Empty
    for b in boxes:
        bb.Union(b.BoundingBox)
    if origin is None:
        origin = rg.Point3d(bb.Max.X + 1.0 * s, bb.Min.Y, bb.Min.Z)
    # shift so the lower left corner of the drawing sits at the origin
    plane = rg.Plane(rg.Point3d(origin.X - bnd[0] * unit, origin.Y - bnd[1] * unit, origin.Z),
                     rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    rd = _RhinoDiagram(plane, unit)
    ztop = rd.draw(items)
    return dict(parts=parts, graph=graph, support=ag.support_graph(graph), byid=byid, ids=ids, name=name,
                boxes=boxes, model_edges=model_edges, frame=frame, items=items, bnd=bnd, plane=plane, unit=unit,
                rd=rd, ztop=ztop, report=ag.report(graph), legend=ag.legend(graph))


# ---------------------------------------------------------------------------
# display handlers: tags, outlines, focus, canvas drawing, clicks

def _uninstall(key=KEY_UI):
    import scriptcontext
    old = scriptcontext.sticky.pop(key, None)
    if not old:
        return
    for obj, name, handler in old.get("subs", []):
        try:
            ev = getattr(obj, name)
            ev -= handler
            setattr(obj, name, ev)
        except Exception:
            pass
    try:
        import gh_interact
        gh_interact.unregister(key)
    except Exception:
        pass


def _visible(ui):
    """None if the component is gone, False if its preview should not show."""
    comp = ui["comp"]
    doc = comp.OnPingDocument()
    if doc is None:
        return None
    if comp.Locked or comp.Hidden:
        return False
    try:
        import Grasshopper
        cv = Grasshopper.Instances.ActiveCanvas
        if cv is not None and cv.Document is not None and cv.Document.DocumentID != doc.DocumentID:
            return False
    except Exception:
        pass
    return True


def _set_focus(ui, n):
    """Toggle the focus on node n (None clears) and recompute the component."""
    import scriptcontext
    from Grasshopper.Kernel import GH_Document
    cur = scriptcontext.sticky.get(KEY_SEL)
    scriptcontext.sticky[KEY_SEL] = None if (n is None or n == cur) else n
    comp = ui["comp"]
    doc = comp.OnPingDocument()
    if doc is not None:
        doc.ScheduleSolution(1, GH_Document.GH_ScheduleDelegate(lambda _d: comp.ExpireSolution(False)))


def _depth(p, cam, cdir):
    return (p.X - cam.X) * cdir.X + (p.Y - cam.Y) * cdir.Y + (p.Z - cam.Z) * cdir.Z


def _pick_view(ui, vp, x, y):
    """Part under the screen point: tag first, then diagram node, then the nearest box."""
    best = None
    for p, text, n in ui["dots"]:
        c = vp.WorldToClient(p)
        w, h = 7.5 * len(text) + 14, 20
        d = abs(c.X - x) + abs(c.Y - y)
        if abs(c.X - x) <= w / 2 and abs(c.Y - y) <= h / 2 and (best is None or d < best[0]):
            best = (d, n)
    if best:
        return best[1]
    line = vp.ClientToWorld(rg.Point2d(x, y))
    from Rhino.Geometry.Intersect import Intersection
    plane = ui["plane"]
    try:
        ok, t = Intersection.LinePlane(line, plane)
        if ok:
            ok2, u, v = plane.ClosestParameter(line.PointAt(t))
            n = gd.pick(ui["items"], u / ui["unit"], v / ui["unit"])
            if n:
                return n
    except Exception:
        pass
    cam, cdir = vp.CameraLocation, vp.CameraDirection
    tol = RhinoDoc.ActiveDoc.ModelAbsoluteTolerance if RhinoDoc.ActiveDoc else 0.001
    for box, n in ui["boxes"]:
        try:
            ok, iv = Intersection.LineBox(line, box, tol)
        except Exception:
            continue
        if not ok:
            continue
        depth = min(_depth(line.PointAt(iv.T0), cam, cdir), _depth(line.PointAt(iv.T1), cam, cdir))
        if best is None or depth < best[0]:
            best = (depth, n)
    return best[1] if best else None


def _hud_lines(ui):
    return ui.get("focus_lines") or []


def _draw_panel_2d(d, x, y, lines):
    """Panel with the focus in the top left corner of a viewport."""
    lh, size, sq = 25, 18, 13
    w = max(len(t) for _, t in lines) * 0.5 * size + 3 * sq + 20
    try:
        d.Draw2dRectangle(sd.Rectangle(int(x - 12), int(y - 10), int(w), int(lh * len(lines) + 16)),
                          sd.Color.FromArgb(255, 200, 200, 196), 1, sd.Color.FromArgb(238, 255, 255, 255))
    except Exception:
        pass
    ink = _color(ag.INK)
    for i, (role, t) in enumerate(lines):
        yy = y + i * lh
        if role:
            c = _color(ag.ROLE_COLOR[role])
            try:
                d.Draw2dRectangle(sd.Rectangle(int(x), int(yy + (lh - sq) / 2 - 2), sq, sq), c, 1, c)
            except Exception:
                pass
        try:
            d.Draw2dText(t, ink if role or i == 0 else _color(ag.INK_MUTED), rg.Point2d(x + sq + 9, yy + lh / 2 - 2),
                         False, size, "Times New Roman")
        except Exception:
            d.Draw2dText(t, ink, rg.Point2d(x + sq + 9, yy + lh / 2 - 2), False)


def _install(ui):
    """Install the display and mouse handlers for this component (replacing earlier ones)."""
    import scriptcontext
    _uninstall(KEY_UI)
    subs = []
    errors = []
    DP = Rhino.Display.DisplayPipeline

    def gone():
        _uninstall(KEY_UI)

    # outlines, depth tested (missing parts, part in focus)
    def post_objects(sender, e):
        try:
            vis = _visible(ui)
            if vis is None:
                return gone()
            if not vis:
                return
            for brep, mat in ui["ghosts"]:
                e.Display.DrawBrepShaded(brep, mat)
            for box, col, thick in ui["wires"]:
                e.Display.DrawBox(box, col, thick)
        except Exception:
            pass

    # tags, focus lines and panel on top of everything
    def foreground(sender, e):
        try:
            vis = _visible(ui)
            if vis is None:
                return gone()
            if not vis:
                return
            d = e.Display
            for a, b, col in ui["lines"]:
                d.DrawLine(a, b, col, 4)
            for p, col in ui["joints"]:
                try:
                    d.DrawPoint(p, Rhino.Display.PointStyle.RoundSimple, 4, col)
                except Exception:
                    d.DrawPoint(p, col)
            for p, col in ui["points"]:
                try:
                    d.DrawPoint(p, Rhino.Display.PointStyle.RoundSimple, 5, col)
                except Exception:
                    d.DrawPoint(p, col)
            for p, text, fill, txt in ui["tags"]:
                d.DrawDot(p, text, fill, txt)
            lines = _hud_lines(ui)
            if lines:
                _draw_panel_2d(d, 22, 44, lines)
        except Exception:
            pass

    try:
        h1 = System.EventHandler[Rhino.Display.DrawEventArgs](post_objects)
        h2 = System.EventHandler[Rhino.Display.DrawEventArgs](foreground)
        DP.PostDrawObjects += h1
        subs.append((DP, "PostDrawObjects", h1))
        DP.DrawForeground += h2
        subs.append((DP, "DrawForeground", h2))
        ui["conduit_ok"] = True
    except Exception as ex:
        ui["conduit_ok"] = False
        errors.append("viewport tags: " + repr(ex))

    # clicks in the Rhino viewports
    ui["mouse_ok"] = False
    if ui["interactive"]:
        def on_click(e):
            if _visible(ui) is not True:
                return False
            pt = e.ViewportPoint
            n = _pick_view(ui, e.View.ActiveViewport, pt.X, pt.Y)
            if n is None:
                return False
            _set_focus(ui, n)
            return True
        try:
            import gh_interact
            ui["mouse_ok"] = gh_interact.register(KEY_UI, on_click)
            if not ui["mouse_ok"]:
                errors.append("viewport clicks: " + str(gh_interact.ERROR))
        except Exception as ex:
            errors.append("viewport clicks: " + repr(ex))

    # canvas drawing and clicks on it
    if ui["canvas_items"]:
        try:
            _install_canvas(ui, subs)
        except Exception as ex:
            errors.append("canvas: " + repr(ex))

    scriptcontext.sticky[KEY_UI] = {"subs": subs}
    try:
        RhinoDoc.ActiveDoc.Views.Redraw()
    except Exception:
        pass
    return errors


def _install_canvas(ui, subs):
    import Grasshopper
    import System.Drawing.Drawing2D as d2d
    import System.Drawing.Text as dtext
    from Grasshopper.GUI.Canvas import GH_Canvas

    comp = ui["comp"]
    canvas = Grasshopper.Instances.ActiveCanvas
    if canvas is None:
        return
    x0, y0, x1, y1 = ui["bnd"]
    k = ui["canvas_width"] / (x1 - x0)
    fonts = {}

    def font(size, bold=False, px=False):
        fk = (round(size, 2), bool(bold), px)
        if fk not in fonts:
            fonts[fk] = sd.Font("Times New Roman", float(size if px else size * k * 1.35),
                                sd.FontStyle.Bold if bold else sd.FontStyle.Regular, sd.GraphicsUnit.Pixel)
        return fonts[fk]

    def pen(color, w, dash=None):
        p = sd.Pen(_color(color), float(max(w * k, 0.5)))
        p.StartCap = d2d.LineCap.Round
        p.EndCap = d2d.LineCap.Round
        p.LineJoin = d2d.LineJoin.Round
        if dash == "dash":
            p.DashPattern = System.Array[System.Single]([4.0, 3.0])
        elif dash == "dot":
            p.DashPattern = System.Array[System.Single]([1.0, 2.5])
        return p

    def frame_origin():
        b = comp.Attributes.Bounds
        return b.Left, b.Bottom + 16

    def paint(sender):
        try:
            if comp.OnPingDocument() is None:
                _uninstall(KEY_UI)
                return
            items = ui["canvas_items"]
            left, top = frame_origin()

            def P(p):
                return sd.PointF(float(left + (p[0] - x0) * k), float(top + (y1 - p[1]) * k))

            g = sender.Graphics
            g.SmoothingMode = d2d.SmoothingMode.AntiAlias
            g.TextRenderingHint = dtext.TextRenderingHint.AntiAlias
            frame = sd.RectangleF(float(left), float(top), float((x1 - x0) * k), float((y1 - y0) * k))
            g.FillRectangle(sd.Brushes.White, frame)
            g.DrawRectangle(sd.Pens.Silver, frame.X, frame.Y, frame.Width, frame.Height)
            for it in items:
                t = it["t"]
                if t == "circle":
                    c = P(it["c"])
                    r = float(it["r"] * k)
                    rect = sd.RectangleF(c.X - r, c.Y - r, 2 * r, 2 * r)
                    br = sd.SolidBrush(_color(it["fill"]))
                    g.FillEllipse(br, rect)
                    br.Dispose()
                    if it.get("stroke"):
                        pn = pen(it["stroke"], it["w"])
                        g.DrawEllipse(pn, rect)
                        pn.Dispose()
                elif t in ("poly", "line"):
                    arr = System.Array[sd.PointF]([P(p) for p in it["pts"]])
                    if t == "poly":
                        if it.get("fill"):
                            br = sd.SolidBrush(_color(it["fill"]))
                            g.FillPolygon(br, arr)
                            br.Dispose()
                        if it.get("stroke"):
                            pn = pen(it["stroke"], it["w"], it.get("dash"))
                            g.DrawPolygon(pn, arr)
                            pn.Dispose()
                    else:
                        pn = pen(it["color"], it["w"], it.get("dash"))
                        g.DrawLines(pn, arr)
                        pn.Dispose()
                elif t == "text":
                    fmt = sd.StringFormat()
                    fmt.LineAlignment = sd.StringAlignment.Center
                    fmt.Alignment = {"middle": sd.StringAlignment.Center, "end": sd.StringAlignment.Far}.get(
                        it.get("anchor"), sd.StringAlignment.Near)
                    br = sd.SolidBrush(_color(it["color"]))
                    g.DrawString(it["s"], font(it["size"], it.get("bold")), br, P(it["pos"]), fmt)
                    br.Dispose()
            # focus panel under the drawing
            lines = _hud_lines(ui)
            if lines:
                lh = 17.0
                py = top + frame.Height + 8
                panel = sd.RectangleF(float(left), float(py), frame.Width, float(lh * len(lines) + 12))
                g.FillRectangle(sd.Brushes.White, panel)
                g.DrawRectangle(sd.Pens.Silver, panel.X, panel.Y, panel.Width, panel.Height)
                for i, (role, t) in enumerate(lines):
                    yy = float(py + 6 + i * lh)
                    if role:
                        br = sd.SolidBrush(_color(ag.ROLE_COLOR[role]))
                        g.FillRectangle(br, float(left + 10), yy + 3.5, 10.0, 10.0)
                        br.Dispose()
                    br = sd.SolidBrush(_color(ag.INK if role or i == 0 else ag.INK_MUTED))
                    g.DrawString(t, font(13, i == 0, True), br, sd.PointF(float(left + 27), yy))
                    br.Dispose()
        except Exception:
            pass

    def mouse_down(sender, e):
        try:
            if not ui["interactive"] or e.Button != System.Windows.Forms.MouseButtons.Left:
                return
            if comp.OnPingDocument() is None:
                return
            pt = canvas.Viewport.UnprojectPoint(sd.PointF(float(e.X), float(e.Y)))
            left, top = frame_origin()
            if not (left <= pt.X <= left + (x1 - x0) * k and top <= pt.Y <= top + (y1 - y0) * k):
                return
            try:
                if canvas.Document.FindAttribute(pt, True) is not None:
                    return  # a Grasshopper object lies over the drawing
            except Exception:
                pass
            x = x0 + (pt.X - left) / k
            y = y1 - (pt.Y - top) / k
            n = gd.pick(ui["items"], x, y)
            if n is not None:
                _set_focus(ui, n)
            elif ui.get("focus_lines"):
                _set_focus(ui, None)
        except Exception:
            pass

    h_paint = GH_Canvas.CanvasPostPaintObjectsEventHandler(paint)
    canvas.CanvasPostPaintObjects += h_paint
    subs.append((canvas, "CanvasPostPaintObjects", h_paint))
    if ui["interactive"]:
        import clr
        try:
            clr.AddReference("System.Windows.Forms")
        except Exception:
            pass
        import System.Windows.Forms  # noqa: F401
        h_mouse = System.Windows.Forms.MouseEventHandler(mouse_down)
        canvas.MouseDown += h_mouse
        subs.append((canvas, "MouseDown", h_mouse))
    canvas.Refresh()


# ---------------------------------------------------------------------------
# run

_path = str(json_path).strip().strip('"') if globals().get("json_path") else ""  # noqa: F821
model = model_colors = model_tags = model_graph = model_graph_colors = None
diagram = diagram_colors = graph = support = report = legend = pdf = svg = None
selected = affected = selection = None

if not _ready:
    report = "Creating inputs and outputs, the component recomputes in a moment."
elif not _path:
    report = "Connect a File Path with the JSON to json_path."
    _uninstall()
elif not os.path.isfile(_path):
    report = "File not found: " + _path
    _uninstall()
else:
    import scriptcontext

    s = RhinoMath.UnitScale(UnitSystem.Meters, RhinoDoc.ActiveDoc.ModelUnitSystem)
    _geo = globals().get("show_geometric")
    _geo = True if _geo is None else bool(_geo)
    _unit = float(globals().get("graph_scale") or 0.2) * s
    _origin = globals().get("graph_origin")
    _okey = (round(_origin.X, 6), round(_origin.Y, 6), round(_origin.Z, 6)) if _origin is not None else None
    _pkg_dir = os.path.dirname(graph_drawing.__file__)
    _code_m = tuple(_mtime(f) for f in (os.path.join(_pkg_dir, "drawing.py"), os.path.join(_pkg_dir, "layouts.py"),
                                        os.path.join(_pkg_dir, "frames.py"), os.path.join(_pkg_dir, "rhino", "conversion.py"),
                                        os.path.join(_code_dir, "component.py")))
    _ckey = (_path, _mtime(_path), _geo, _unit, _okey, s, _code_m)
    _cache = scriptcontext.sticky.get(KEY_CACHE)
    _needed = ("graph", "items", "boxes", "model_edges", "frame", "rd")
    if not _cache or _cache.get("key") != _ckey or any(k not in _cache for k in _needed):
        _cache = _build(_path, _geo, s, _unit, _origin)
        _cache["key"] = _ckey
        scriptcontext.sticky[KEY_CACHE] = _cache
    C = _cache
    graph, support, legend = C["graph"], C["support"], C["legend"]
    _byid, _ids = C["byid"], C["ids"]
    _lines = [C["report"]]
    if C["rd"].text_failed:
        _lines.append("text as surfaces failed, the diagram uses TextDots")

    # focus: `select` when it changes, otherwise the last click
    _sel_in = str(globals().get("select") or "").strip()
    if _sel_in != scriptcontext.sticky.get(KEY_SEL_IN, ""):
        scriptcontext.sticky[KEY_SEL_IN] = _sel_in
        scriptcontext.sticky[KEY_SEL] = ag.find_node(graph, _sel_in)
        if _sel_in and scriptcontext.sticky[KEY_SEL] is None:
            _lines.append("select: no part '%s'" % _sel_in)
    _sel = scriptcontext.sticky.get(KEY_SEL)
    if _sel is not None and not graph.has_node(_sel):
        _sel = None
    _f = ag.focus(graph, _sel, bool(globals().get("chain")))
    _roles = _f["roles"] if _f else {}

    # model, coloured by state, or by role while a part is in focus
    model = [b.ToBrep() for b in C["boxes"]]
    model_colors = []
    for n in _ids:
        p = _byid[n]
        if not _f:
            model_colors.append(_color(p.fill(), ag.MISSING_ALPHA if p.status == "missing" else 255))
        elif n in _roles:
            model_colors.append(_color(ag.ROLE_COLOR[_roles[n]], 200 if p.status == "missing" else 255))
        else:
            model_colors.append(_color(p.fill(), 30 if p.status == "missing" else 45))

    # tags (TextDots as output; the coloured ones are drawn by the display handler)
    model_tags = []
    _tags, _dots = [], []
    for n in _ids:
        p = _byid[n]
        pt = _pt(p.center, s)
        dot = rg.TextDot(p.code, pt)
        dot.SecondaryText = n
        dot.FontHeight = 11
        model_tags.append(dot)
        fill = p.color
        txt = ag.text_on(fill)
        if p.status == "missing":
            fill, txt = ag.MISSING_TAG, ag.INK
        if _f and n not in _roles:
            fill, txt = gd.blend(fill, 0.8), "#a9a8a3"
        _tags.append((pt, p.code, _color(fill), _color(txt)))
        _dots.append((pt, p.code, n))

    # outlines: missing parts always, the part in focus thick
    _wires, _ghosts = [], []
    for b, n in zip(C["boxes"], _ids):
        if _byid[n].status == "missing" and (not _f or n in _roles):
            _wires.append((b, _color(ag.MISSING_EDGE), 3))
            col = ag.PART_FILL["missing"] if not _f else ag.ROLE_COLOR[_roles[n]]
            _ghosts.append((model[_ids.index(n)], Rhino.Display.DisplayMaterial(_color(col), 0.35)))
    if _f:
        _wires.append((C["boxes"][_ids.index(_sel)], _color(ag.ROLE_COLOR["sel"]), 3))

    # connections on the model; in focus, those of the selected part on top
    _style = str(globals().get("graph_style") or "0").strip().lower()
    _style = {"0": "joint", "1": "liaison", "2": "frame"}.get(_style, _style)
    if _style not in ("joint", "liaison", "frame"):
        _lines.append("graph_style: unknown '%s', using joint" % _style)
        _style = "joint"
    model_graph, model_graph_colors = [], []
    _flines, _fpoints, _joints = [], [], []
    if _style == "frame":
        # members as bars between their joints, coloured by type (by role in focus)
        for n, pts, col in C["frame"]:
            model_graph.append(rg.PolylineCurve(pts))
            role = _roles.get(n)
            if not _f:
                model_graph_colors.append(_color(col))
            elif role:
                model_graph_colors.append(_color(ag.ROLE_COLOR[role]))
                _flines.append((pts[0], pts[1], _color(ag.ROLE_COLOR[role])))
            else:
                model_graph_colors.append(_color(gd.blend(col, 0.85)))
        for u, v, pts, col, cpt in C["model_edges"]:
            mine = _f and _sel in (u, v)
            _joints.append((cpt, _color(ag.INK if (not _f or mine) else gd.blend(ag.INK, 0.8))))
    else:
        for u, v, pts, col, cpt in C["model_edges"]:
            if _style == "liaison":
                pts = [pts[0], pts[2]]
            model_graph.append(rg.PolylineCurve(pts))
            inside = _f and frozenset((u, v)) in _f["edges"]
            model_graph_colors.append(_color(col if (not _f or inside) else gd.blend(col, 0.85)))
            if _f and _sel in (u, v):
                other = v if u == _sel else u
                rc = _color(ag.ROLE_COLOR[_roles.get(other, "touch")])
                _flines += [(a, b, rc) for a, b in zip(pts, pts[1:])]
                if _style == "joint":
                    _fpoints.append((cpt, rc))

    # diagram: base geometry from the cache, recoloured; rings for the focus
    _hitems = ag.highlight(C["items"], _f)
    _n0 = len(C["items"])
    diagram = list(C["rd"].geo)
    diagram_colors = C["rd"].colors(_hitems)
    if len(_hitems) > _n0:
        _rx = _RhinoDiagram(C["plane"], C["unit"])
        _rx.draw(_hitems[_n0:], z0=C["ztop"] + 0.002, first=_n0)
        diagram += _rx.geo
        diagram_colors += _rx.col

    legend = C["legend"]
    if _f:
        selected = _sel
        affected = list(_f["affected"])
        selection = "\n".join(t for _, t in ag.focus_lines(graph, _f))

    # display handlers
    _show = globals().get("show_on_canvas")
    _show = True if _show is None else bool(_show)
    _inter = globals().get("interactive")
    _inter = True if _inter is None else bool(_inter)
    _ui = dict(comp=_comp, tags=_tags, dots=_dots, wires=_wires, ghosts=_ghosts, lines=_flines, points=_fpoints, joints=_joints,
               boxes=list(zip(C["boxes"], _ids)), plane=C["plane"], unit=C["unit"], items=C["items"],
               bnd=C["bnd"], canvas_items=_hitems if _show else None,
               canvas_width=float(globals().get("canvas_width") or 900),
               focus_lines=ag.focus_lines(graph, _f), interactive=_inter)
    _errors = _install(_ui)
    _lines += _errors
    if not _ui.get("conduit_ok"):
        for _p in _comp.Params.Output:  # fall back to the plain TextDots
            if _p.NickName == "model_tags":
                _p.Hidden = False

    if globals().get("export"):
        _gh = _comp.OnPingDocument().FilePath
        if not _gh:
            _lines.append("save the .gh file first, the files go into a Graph folder next to it")
        else:
            _folder = os.path.join(os.path.dirname(_gh), "Graph")
            if not os.path.isdir(_folder):
                os.makedirs(_folder)
            _exp = ag.highlight(C["items"], None)
            pdf = export.to_pdf(_exp, C["bnd"], os.path.join(_folder, C["name"] + ".pdf"))
            svg = os.path.join(_folder, C["name"] + ".svg")
            with open(svg, "w", encoding="utf-8") as f:
                f.write(export.to_svg(_exp, C["bnd"]))
    report = "\n".join(_lines)

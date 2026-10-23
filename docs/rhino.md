# Rhino and Grasshopper

## With a COMPAS scene

Importing [`graph_drawing.rhino`][graph_drawing.rhino] registers scene objects
for drawings, so a drawing can be added to a `compas.scene.Scene` like any
COMPAS object:

```python
from compas.scene import Scene
import graph_drawing.rhino  # registers the drawing for Rhino and Grasshopper
from graph_drawing import frames

scene = Scene()
obj = scene.add(frames.drawing(json_path), unit=0.2)
geometry = scene.draw()
colors = obj.colors  # one per piece of geometry, for a Custom Preview
```

In Grasshopper `scene.draw()` returns the geometry. In Rhino, outside
Grasshopper, it adds the pieces to the document, each in its own colour.
[`to_rhino(drawing, plane, unit)`][graph_drawing.rhino.conversion.to_rhino]
gives geometry and colours directly.

COMPAS looks for scene objects only in packages whose name starts with
"compas", so importing `graph_drawing.rhino` registers them itself, after the
COMPAS ones.

## The Grasshopper component

`rhino/` in the repository holds a Grasshopper component built on the package.
It reads a JSON of parts as boxes and shows the structure as boxes coloured by
state, tags, the connections on the model, the support drawing next to the
model and on the canvas below the component, a report, and a focus on one part
with what it rests on and what rests on it.

1. In Grasshopper add a **Script** component, double-click it, choose
   **Python 3**, paste `rhino/stub.py` and close the editor. Save the .gh file
   in the repository's `rhino` folder or next to it, so the stub finds
   `rhino/component.py` (or set the environment variable `GRAPH_DRAWING_RHINO`
   to that folder). If graph_drawing is not installed in Rhino's Python, the
   stub adds the repository's `src` folder to the path.
2. Connect a **File Path** with `data/timber_corner_structure.json` to
   `json_path` once the inputs appear.

On the first run the component creates its inputs and outputs, places three
**Custom Preview** components next to itself and wires them, then recomputes
once. Edits to the package and to `rhino/component.py` take effect on the next
recompute; `rhino/gh_interact.py` (the mouse callback, a .NET type) needs a
Rhino restart.

| Input | |
|---|---|
| `json_path` | File Path to the JSON, the only required input |
| `show_geometric` | also show contacts the JSON does not list (default True) |
| `graph_origin` | lower left corner of the drawing in the XY plane (default: right of the model) |
| `graph_scale` | metres per drawing unit (default 0.2; a node has a radius of 0.3 units) |
| `show_on_canvas` | the drawing below the component (default True) |
| `canvas_width` | width of that drawing (default 900) |
| `export` | PDF and SVG into a `Graph` folder next to the .gh file |
| `select` | code or id of a part to focus on; takes effect when the value changes |
| `interactive` | clicks in the viewport and on the canvas drawing (default True) |
| `graph_style` | connections on the model: 0 joint (default), 1 liaison, 2 frame |
| `chain` | also mark the parts that lose all support from below once the selected one is out |

Outputs: `model`, `model_colors`, `model_tags`, `model_graph`,
`model_graph_colors`, `diagram`, `diagram_colors`, `graph` (COMPAS Graph of the
contacts), `support` (COMPAS Graph, u → v means u rests on v), `report`,
`legend`, `pdf`, `svg`, `selected`, `affected`, `selection`.

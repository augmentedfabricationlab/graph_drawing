# Installation

Graph Drawing needs Python 3.9 or newer and [COMPAS](https://compas.dev)
2.15.1 or newer. [compas_model](https://github.com/blockresearchgroup/compas_model)
is needed only for [`from_model`][graph_drawing.models.from_model].

## User

Clone the repository and install it into your environment:

```bash
git clone https://github.com/augmentedfabricationlab/graph_drawing.git
pip install -e graph_drawing
```

With compas_model, for drawing models:

```bash
pip install -e graph_drawing[model]
```

## Rhino 8 and Grasshopper

Rhino 8 runs Python 3.9. Find its Python with

```bash
python -m compas_rhino.print_python_path
```

It looks like `C:/Users/your_user_name/.rhinocode/py39-rh8/python.exe`.
Install the package there as well:

```bash
path/to/rhino/python -m pip install -e graph_drawing
```

Or open any Python 3 script in Rhino 8, go to *Tools, Options* in the script
editor and add the `src` folder of the repository to the Python path. The
Grasshopper component finds `src` on its own, see
[Rhino and Grasshopper](rhino.md).

## Developer

The repository follows the template of the Augmented Fabrication Lab. Install
the development dependencies, which include the tools for this documentation,
and make the project available in Rhino 8:

```bash
pip install -r requirements-dev.txt
invoke add-to-rhino
```

Recurring tasks run with [invoke](https://www.pyinvoke.org):

| Task | |
|---|---|
| `invoke test` | all checks and all tests (the parts that need Rhino are not tested) |
| `invoke check` | README, flake8, import order and MANIFEST.in |
| `invoke docs` | this documentation, into `dist/docs` |
| `invoke clean` | remove generated files |
| `invoke release patch` | raise the version, test, build and upload |
| `invoke add-to-rhino` | install the project into the Python of Rhino 8 |

`mkdocs serve` shows the documentation while you write it. Every push to
master runs the tests and publishes the documentation to GitHub Pages.

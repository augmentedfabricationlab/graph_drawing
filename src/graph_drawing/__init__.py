"""
********************************************************************************
graph_drawing
********************************************************************************

Schematic drawings of graphs for Rhino, Grasshopper, SVG and PDF: sequences of
actions, programs of interventions, structures and their connections, and support graphs
of timber frames.


Setup
=====

Install it in editable mode into the Python that Rhino 8 uses (see README.rst)::

    pip install -e .


Main concepts
=============

A drawing is made in three steps, the same for every kind of graph:

1. A **graph** (:class:`compas.datastructures.Graph`) whose nodes and edges
   carry styling attributes: label, fill, ring, shape; colour, dash, arrow.
   :mod:`graph_drawing.frames` makes one from a JSON of parts as boxes,
   :func:`from_model` from a compas_model model with the state of an intervention on its
   graph, :func:`steps` from a list of steps.
2. A **layout** gives every node a position: :func:`graph_drawing.layouts.support`
   draws the support hierarchy of a frame after Bruun et al. 2024,
   :func:`graph_drawing.layouts.layered` puts the steps of a directed graph in layers.
3. :func:`draw` turns graph and positions into a :class:`Drawing`: a list of
   plain items (circles, polygons, lines, text) that is written as SVG or PDF
   (:mod:`graph_drawing.export`) or drawn in Rhino and Grasshopper
   (:mod:`graph_drawing.rhino`, only inside Rhino).

Documentation: https://augmentedfabricationlab.github.io/graph_drawing/latest/

"""

from __future__ import print_function

from . import export
from . import frames
from . import layouts
from . import models
from .__version__ import __author__
from .__version__ import __author_email__
from .__version__ import __copyright__
from .__version__ import __description__
from .__version__ import __license__
from .__version__ import __title__
from .__version__ import __url__
from .__version__ import __version__
from .drawing import Drawing
from .drawing import draw
from .models import from_model
from .models import steps

__all__ = [
    "Drawing",
    "draw",
    "export",
    "frames",
    "layouts",
    "models",
    "from_model",
    "steps",
    "__author__",
    "__author_email__",
    "__copyright__",
    "__description__",
    "__license__",
    "__title__",
    "__url__",
    "__version__",
]

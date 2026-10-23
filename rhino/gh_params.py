"""
Let a Rhino 8 Script component (Python 3) create its own inputs and outputs,
and the Custom Preview components that colour its geometry.

Call ensure_params(ghenv.Component, INPUTS, OUTPUTS, PREVIEWS) at the top of a
script. If the component already has exactly these parameters it returns True
and the script runs normally. Otherwise it schedules a rebuild right after the
current solution and returns False; the component then recomputes with the new
parameters. Parameters are created through the component's own factory
(IGH_VariableParameterComponent.CreateParameter), the same path as the zoomable
"+" buttons. Existing parameters with a matching name keep their wires. The
standard output "out" is left alone.

Spec format
    INPUTS    (name, description, optional)
    OUTPUTS   (name, description[, preview])   preview False hides the output
              in the viewport (it is shown through a Custom Preview instead)
    PREVIEWS  (geometry output, colour output) pairs; a Custom Preview is
              placed next to the component and wired, unless one exists
"""

import System.Drawing as sd
from Grasshopper.Kernel import GH_Document, GH_ParameterSide

KEEP = ("out",)  # Rhino 8 console output


def _names(params):
    return [p.NickName for p in params if p.NickName not in KEEP]


def _matches(comp, inputs, outputs):
    return (_names(comp.Params.Input) == [s[0] for s in inputs]
            and _names(comp.Params.Output) == [s[0] for s in outputs])


def _sync(comp, side, spec):
    params = comp.Params.Input if side == GH_ParameterSide.Input else comp.Params.Output
    wanted = [s[0] for s in spec]
    for p in list(params):
        if p.NickName not in wanted and p.NickName not in KEEP:
            if side == GH_ParameterSide.Input:
                comp.Params.UnregisterInputParameter(p, True)
            else:
                comp.Params.UnregisterOutputParameter(p, True)
    for i, s in enumerate(spec):
        name, desc = s[0], s[1]
        existing = [p for p in params if p.NickName == name]
        if existing:
            p = existing[0]
        else:
            n_keep = sum(1 for q in params if q.NickName in KEEP)  # "out" sits first
            index = min(i + n_keep, params.Count)
            p = comp.CreateParameter(side, index)
            if side == GH_ParameterSide.Input:
                comp.Params.RegisterInputParam(p, index)
            else:
                comp.Params.RegisterOutputParam(p, index)
        p.Name = name
        p.NickName = name
        p.Description = desc
        if side == GH_ParameterSide.Input:
            p.Optional = bool(s[2]) if len(s) > 2 else True
        elif len(s) > 2:
            try:
                p.Hidden = not bool(s[2])
            except Exception:
                pass


def _output(comp, name):
    for p in comp.Params.Output:
        if p.NickName == name:
            return p
    return None


def _has_custom_preview(param):
    for r in param.Recipients:
        obj = r.Attributes.GetTopLevel.DocObject
        if "CustomPreview" in obj.GetType().Name:
            return True
    return False


def ensure_previews(comp, doc, previews):
    """Add and wire one Custom Preview per (geometry, colour) output pair."""
    try:
        from Grasshopper.Kernel.Components import GH_CustomPreviewComponent
    except Exception:
        return
    b = comp.Attributes.Bounds
    for i, (geo_name, col_name) in enumerate(previews):
        geo, col = _output(comp, geo_name), _output(comp, col_name)
        if geo is None or col is None or _has_custom_preview(geo):
            continue
        cp = GH_CustomPreviewComponent()
        cp.CreateAttributes()
        cp.Attributes.Pivot = sd.PointF(b.Right + 120, b.Top + 30 + 60 * i)
        doc.AddObject(cp, False)
        cp.Params.Input[0].AddSource(geo)
        cp.Params.Input[1].AddSource(col)
        cp.ExpireSolution(False)


def _apply_preview_flags(comp, outputs):
    flags = {s[0]: bool(s[2]) for s in outputs if len(s) > 2}
    for p in comp.Params.Output:
        if p.NickName in flags:
            try:
                if p.Hidden == flags[p.NickName]:
                    p.Hidden = not flags[p.NickName]
            except Exception:
                pass


def ensure_params(comp, inputs, outputs, previews=()):
    if _matches(comp, inputs, outputs):
        _apply_preview_flags(comp, outputs)
        return True
    doc = comp.OnPingDocument()
    if doc is None:
        return False

    def rebuild(_doc):
        _sync(comp, GH_ParameterSide.Input, inputs)
        _sync(comp, GH_ParameterSide.Output, outputs)
        comp.VariableParameterMaintenance()
        comp.Params.OnParametersChanged()
        comp.Attributes.ExpireLayout()
        comp.Attributes.PerformLayout()
        if previews:
            try:
                ensure_previews(comp, doc, previews)
            except Exception:
                pass
        comp.ExpireSolution(False)

    doc.ScheduleSolution(5, GH_Document.GH_ScheduleDelegate(rebuild))
    return False

"""
One mouse callback for the whole Rhino session, shared by all graph_drawing
components. Each component registers a click handler under its own key;
the callback asks them in turn and cancels Rhino's own handling of the
click when one of them used it.

This module is imported once and never reloaded: a Python class derived from
a .NET class becomes a .NET type, which cannot be defined twice in a session.
Handlers live in the plain dict HANDLERS, so the components can replace them
on every run.
"""

import Rhino

HANDLERS = {}  # key -> function(MouseCallbackEventArgs) -> True if used
ERROR = None
_callback = None


def _on_down(e):
    if e.MouseButton != Rhino.UI.MouseButton.Left:
        return
    if e.ShiftKeyDown or e.CtrlKeyDown:
        return
    try:
        if Rhino.Commands.Command.InCommand():
            return
    except Exception:
        pass
    for key, handler in list(HANDLERS.items()):
        try:
            if handler(e):
                e.Cancel = True
                return
        except Exception:
            pass


_classes = []
try:
    class _ClickNS(Rhino.UI.MouseCallback):
        __namespace__ = "GraphDrawingInteract"

        def OnMouseDown(self, e):
            _on_down(e)
    _classes.append(_ClickNS)
except Exception as ex:  # older pythonnet: no __namespace__
    ERROR = repr(ex)
try:
    class _Click(Rhino.UI.MouseCallback):
        def OnMouseDown(self, e):
            _on_down(e)
    _classes.append(_Click)
except Exception as ex:
    ERROR = repr(ex)


def ensure():
    """Switch the callback on. Returns True if clicks can be received."""
    global _callback, ERROR
    if _callback is None:
        for cls in _classes:
            try:
                _callback = cls()
                break
            except Exception as ex:
                ERROR = repr(ex)
    if _callback is None:
        return False
    _callback.Enabled = True
    return True


def register(key, handler):
    HANDLERS[key] = handler
    return ensure()


def unregister(key):
    HANDLERS.pop(key, None)
    if not HANDLERS and _callback is not None:
        _callback.Enabled = False

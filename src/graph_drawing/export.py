"""
SVG and PDF of a drawing, as vector graphics.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from .drawing import hex_rgb

__all__ = ["to_svg", "to_pdf"]


def _dash_array(dash, w, k):
    if dash == "dash":
        return [6 * w * k, 4 * w * k]
    if dash == "dot":
        return [1.2 * w * k, 3 * w * k]
    return None


def to_svg(items, bnd, scale=60.0, font="Times New Roman"):
    """The items as SVG text.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.
    bnd : tuple[float, float, float, float]
        x0, y0, x1, y1 of the drawing.
    scale : float, optional
        Pixels per drawing unit.
    font : str, optional
        Font family of the text.

    Returns
    -------
    str

    """
    x0, y0, x1, y1 = bnd
    W, H = (x1 - x0) * scale, (y1 - y0) * scale

    def P(p):
        return "%.2f,%.2f" % ((p[0] - x0) * scale, (y1 - p[1]) * scale)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" viewBox="0 0 %.2f %.2f">' % (W, H, W, H),
           '<rect width="100%" height="100%" fill="#ffffff"/>']
    for it in items:
        t = it["t"]
        if t == "circle":
            st = ' stroke="%s" stroke-width="%.2f"' % (it["stroke"], it["w"] * scale) if it.get("stroke") else ""
            cx, cy = P(it["c"]).split(",")
            out.append('<circle cx="%s" cy="%s" r="%.2f" fill="%s"%s/>' % (cx, cy, it["r"] * scale, it["fill"], st))
        elif t in ("poly", "line"):
            pts = " ".join(P(p) for p in it["pts"])
            if t == "poly":
                fill = it.get("fill") or "none"
                st = ' stroke="%s" stroke-width="%.2f"' % (it["stroke"], it["w"] * scale) if it.get("stroke") else ""
                da = _dash_array(it.get("dash"), it.get("w", 0.03), scale)
                if da:
                    st += ' stroke-dasharray="%.1f %.1f"' % tuple(da)
                out.append('<polygon points="%s" fill="%s"%s/>' % (pts, fill, st))
            else:
                da = _dash_array(it.get("dash"), it["w"], scale)
                st = ' stroke-dasharray="%.1f %.1f"' % tuple(da) if da else ""
                out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.2f" '
                           'stroke-linecap="round" stroke-linejoin="round"%s/>' % (pts, it["color"], it["w"] * scale, st))
        elif t == "text":
            x, y = P(it["pos"]).split(",")
            anchor = it.get("anchor", "middle")
            out.append('<text xml:space="preserve" x="%s" y="%s" font-family="%s" font-size="%.2f" fill="%s" text-anchor="%s" '
                       'dominant-baseline="central"%s>%s</text>'
                       % (x, y, font, it["size"] * scale * 1.35, it["color"], anchor,
                          ' font-weight="bold"' if it.get("bold") else "",
                          it["s"].replace("&", "&amp;").replace("<", "&lt;")))
    out.append("</svg>")
    return "\n".join(out)


def _rgb(h):
    r, g, b = hex_rgb(h)
    return "%.3f %.3f %.3f" % (r / 255.0, g / 255.0, b / 255.0)


def to_pdf(items, bnd, path, scale=28.0):
    """Write the items as a minimal one-page vector PDF.

    The text uses the standard fonts Times-Roman and Times-Bold, so nothing
    is embedded.

    Parameters
    ----------
    items : list[dict]
        The items of a drawing.
    bnd : tuple[float, float, float, float]
        x0, y0, x1, y1 of the drawing.
    path : str
        The file to write.
    scale : float, optional
        Points per drawing unit.

    Returns
    -------
    str
        The path.

    """
    x0, y0, x1, y1 = bnd
    W, H = (x1 - x0) * scale, (y1 - y0) * scale

    def P(p):
        return (p[0] - x0) * scale, (p[1] - y0) * scale

    ops = ["1 1 1 rg 0 0 %.2f %.2f re f" % (W, H), "1 J 1 j"]
    k = 0.5523
    for it in items:
        t = it["t"]
        if t == "circle":
            cx, cy = P(it["c"])
            r = it["r"] * scale
            path_ = ("%.2f %.2f m " % (cx + r, cy) +
                     "%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx + r, cy + k * r, cx + k * r, cy + r, cx, cy + r) +
                     "%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - k * r, cy + r, cx - r, cy + k * r, cx - r, cy) +
                     "%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - r, cy - k * r, cx - k * r, cy - r, cx, cy - r) +
                     "%.2f %.2f %.2f %.2f %.2f %.2f c h" % (cx + k * r, cy - r, cx + r, cy - k * r, cx + r, cy))
            ops.append("%s rg %s f" % (_rgb(it["fill"]), path_))
            if it.get("stroke"):
                ops.append("[] 0 d %s RG %.2f w %s S" % (_rgb(it["stroke"]), it["w"] * scale, path_))
        elif t in ("poly", "line"):
            pts = [P(p) for p in it["pts"]]
            path_ = "%.2f %.2f m " % pts[0] + " ".join("%.2f %.2f l" % p for p in pts[1:])
            w = it.get("w", 0.03)
            da = _dash_array(it.get("dash"), w, scale)
            dash = "[%.1f %.1f] 0 d" % tuple(da) if da else "[] 0 d"
            if t == "poly":
                path_ += " h"
                if it.get("fill"):
                    ops.append("%s rg %s f" % (_rgb(it["fill"]), path_))
                if it.get("stroke"):
                    ops.append("%s %s RG %.2f w %s S" % (dash, _rgb(it["stroke"]), w * scale, path_))
            else:
                ops.append("%s %s RG %.2f w %s S" % (dash, _rgb(it["color"]), w * scale, path_))
        elif t == "text":
            x, y = P(it["pos"])
            size = it["size"] * scale * 1.35
            width = 0.5 * size * len(it["s"])  # Times-Roman average, good enough for codes
            anchor = it.get("anchor", "middle")
            x -= width / 2 if anchor == "middle" else (width if anchor == "end" else 0)
            s = it["s"].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            font = "/F2" if it.get("bold") else "/F1"
            ops.append("BT %s %.2f Tf %s rg %.2f %.2f Td (%s) Tj ET" % (font, size, _rgb(it["color"]), x, y - size * 0.33, s))
    content = "\n".join(ops).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] /Contents 4 0 R "
         "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (W, H)).encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold >>",
    ]
    data = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs):
        offsets.append(len(data))
        data += b"%d 0 obj\n" % (i + 1) + o + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        data += b"%010d 00000 n \n" % off
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f:
        f.write(data)
    return path

"""
Griffe extension for the documentation: the Sphinx roles of the numpy
docstrings, such as :class:`Split`, become links.

In the type of a parameter or return value the role becomes the plain name,
which mkdocstrings links where it can. In text it becomes a Markdown link to
the object in this package or in COMPAS, and code elsewhere. A literal block
introduced with "::" keeps a single colon, and an indented block that follows
a line of text directly, such as a list of attributes, stays preformatted.
"""

import re

import griffe

ROLE = re.compile(r":(?:py:)?(?:class|func|meth|mod|attr|obj|exc|data|rhino):`(~?)([^`<]+?)\s*(?:<([^>]+)>)?`")
TYPED = ("Parameters", "Other Parameters", "Returns", "Yields", "Receives", "Raises", "Warns", "Attributes")
LINKED = ("compas.",)


def resolve(name, obj):
    """The path of a name as seen from an object, or None."""
    root = obj.package
    head, _, rest = name.partition(".")
    if head == root.name:
        scopes, name = [root], rest
    elif rest:
        return name
    else:
        scopes = [obj, obj.parent, obj.module, root]
    for scope in scopes:
        if scope is None:
            continue
        try:
            member = scope[name] if name else scope
            target = member.final_target if member.is_alias else member
        except Exception:
            continue
        documented = target.is_module or (target.is_public and target.docstring is not None)
        return target.path if documented else None
    return None


def convert(text, obj):
    lines = text.split("\n")
    section = None
    for i, line in enumerate(lines):
        following = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if line.strip() and set(following) == {"-"} and len(following) >= 3:
            section = line.strip()
        typed = section in TYPED and line[:1] not in (" ", "\t")

        def replace(match):
            short, text, target = match.groups()
            if typed:
                return (target or text).lstrip("~")
            path = resolve((target or text).lstrip("~"), obj)
            title = text if target else (text.rsplit(".", 1)[-1] if short else text)
            if path and (path.split(".")[0] == obj.package.name or path.startswith(LINKED)):
                return "[`{}`][{}]".format(title, path)
            return "`{}`".format(title)

        line = ROLE.sub(replace, line)
        if line.rstrip().endswith("::"):
            line = line.rstrip()[:-1].rstrip(":") + (":" if line.strip() != "::" else "")
        elif not typed and line.strip() and line[:1] != " " and lines[i + 1:i + 2] and lines[i + 1].startswith("    ") and lines[i + 1].strip():
            line += "\n"
        lines[i] = line
    return "\n".join(lines)


class SphinxRoles(griffe.Extension):
    def on_object(self, *, obj, **kwargs):
        if obj.docstring is not None:
            obj.docstring.value = convert(obj.docstring.value, obj)

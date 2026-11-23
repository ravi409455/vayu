"""Values in report text: `{{ inspection.colour }}`, `{{ sys.booking_id }}`, nothing more.

Rendered by Jinja2's sandbox with autoescape, after a check that the text holds only plain
variable lookups: no tags, filters, calls or arithmetic, so a template cannot do anything but
show values. Rich text is cleaned to a small set of tags when it is saved."""
from typing import Any

import nh3
from jinja2 import ChainableUndefined, TemplateSyntaxError, nodes
from jinja2.sandbox import SandboxedEnvironment

ROOTS = {"booking", "start", "inspection", "end", "sys"}
ALLOWED_NODES = (nodes.Template, nodes.Output, nodes.TemplateData, nodes.Name, nodes.Getattr)
TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "a", "span", "h2", "h3",
        "h4", "blockquote", "hr"}
CLASSES = {"tone-brand", "tone-ok", "tone-warn", "tone-bad", "tone-muted", "small", "large"}

_env = SandboxedEnvironment(autoescape=True, undefined=ChainableUndefined)
_plain = SandboxedEnvironment(autoescape=False, undefined=ChainableUndefined)


def check(text: str, where: str) -> None:
    """Raises ValueError unless the text uses only `{{ root.name }}` placeholders."""
    try:
        tree = _env.parse(text)
    except TemplateSyntaxError as e:
        raise ValueError(f"{where}: {e.message} (line {e.lineno}).") from e
    for node in tree.find_all(nodes.Node):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"{where}: only values like {{{{ inspection.colour }}}} are allowed.")
        if isinstance(node, nodes.Name) and node.name not in ROOTS:
            raise ValueError(f"{where}: '{node.name}' is not something a report can show; use "
                             f"{', '.join(sorted(ROOTS))}.")


def refs(text: str) -> set[tuple[str, str]]:
    """(form, key) of every form value the text shows (sys values are not form fields)."""
    out: set[tuple[str, str]] = set()
    for node in _env.parse(text).find_all(nodes.Getattr):
        if isinstance(node.node, nodes.Name) and node.node.name != "sys":
            out.add((node.node.name, node.attr))
    return out


def render(text: str, values: dict[str, Any], html: bool = True) -> str:
    return (_env if html else _plain).from_string(text).render(**values)


def _class_ok(tag: str, attr: str, value: str) -> str | None:
    if attr == "class":
        kept = [c for c in value.split() if c in CLASSES]
        return " ".join(kept) or None
    return value


def clean_html(html: str) -> str:
    """The allowed subset of HTML; everything else is dropped (scripts, styles, images...)."""
    return nh3.clean(html, tags=TAGS, attributes={"a": {"href"}, "span": {"class"}, "p": {"class"}},
                     url_schemes={"https", "mailto", "tel"}, attribute_filter=_class_ok,
                     link_rel="noopener noreferrer")

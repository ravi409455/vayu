"""Values in report text: `{{ inspection.colour }}`, `{{ sys.booking_id }}`, nothing more.

Rendered by Jinja2's sandbox with autoescape, after a check that the text holds only plain
variable lookups: no tags, filters, calls or arithmetic, so a template cannot do anything but
show values. Rich text is cleaned to a small set of tags when it is saved."""
import re
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


CUSTOM_TAGS = {"div", "span", "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "small", "sup",
               "sub", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "table", "thead",
               "tbody", "tfoot", "tr", "th", "td", "colgroup", "col", "caption", "section",
               "figure", "figcaption"}
# anything in CSS that could load a file: url(), image(), image-set(), @import; backslash
# escapes (u\rl) and '<' are refused too, so none of these can be spelled another way
NO_FETCH = re.compile(r"url\s*\(|image(-set)?\s*\(|@import|expression|\\|<", re.I)
# inline style keeps only layout and typography: nothing that takes a picture
STYLE_PROPS = {
    "color", "background-color", "opacity", "font", "font-family", "font-size", "font-style",
    "font-weight", "font-variant", "text-align", "text-decoration", "text-transform",
    "text-indent", "line-height", "letter-spacing", "word-spacing", "white-space",
    "vertical-align", "display", "width", "height", "min-width", "max-width", "min-height",
    "max-height", "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border", "border-top", "border-right", "border-bottom", "border-left", "border-color",
    "border-width", "border-style", "border-radius", "border-collapse", "border-spacing",
    "page-break-before", "page-break-after", "page-break-inside", "break-before",
    "break-after", "break-inside", "columns", "column-count", "column-gap", "table-layout",
    "box-sizing", "float", "clear", "gap", "flex", "flex-direction", "flex-wrap",
    "justify-content", "align-items", "list-style-type"}
STYLE_ATTR = re.compile(r'style="([^"]*)"')


def clean_custom(html: str) -> str:
    """Custom HTML: layout tags with class and style, nothing that runs, links or loads."""
    html = nh3.clean(html, tags=CUSTOM_TAGS, url_schemes=set(), filter_style_properties=STYLE_PROPS,
                     attributes={"*": {"class", "style"}, "td": {"colspan", "rowspan"},
                                 "th": {"colspan", "rowspan"}, "col": {"span"}})
    for style in STYLE_ATTR.findall(html):
        if NO_FETCH.search(style):
            raise ValueError("Custom HTML cannot load pictures or files (no url(...) or escapes).")
        if "{" in style:            # a value filled in later could carry url(...): not in style
            raise ValueError("Custom HTML cannot put values like {{ ... }} inside style=\"\".")
    return html


def check_css(css: str, where: str) -> None:
    """Custom CSS stays inside its part: no loading, no escapes, braces that close."""
    if NO_FETCH.search(css):
        raise ValueError(f"{where}: CSS cannot use url(...), image(...), @import, backslashes "
                         "or '<'.")
    depth = 0
    for ch in css:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            break
    if depth:
        raise ValueError(f"{where}: the {{ and }} in the CSS do not match.")

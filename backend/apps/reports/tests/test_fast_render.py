"""The faster PDF (2026-11-27): photo grids as fixed tables, photos and fonts handed to the
renderer as bytes, no garbage sweeps while a PDF is drawn. The pages and their text must stay
what they were: measured identical, page by page, on real 150-photo reports before this went in."""
import gc
import io
import re
from unittest import mock

import pypdf

from apps.media import storage
from apps.reports import context, render

from .test_reports import complete_job, one_page, renv, source  # noqa: F401

PHOTOS = {"type": "photos", "per_row": 3, "source": {"kind": "fields", "fields": ["inspection.photo_a"]}}


def build(b, *parts):
    src = source(b)
    d = one_page(*parts)
    return render.render_html(context.build(src, d), d, src.values())


def test_photos_are_named_in_the_html_and_kept_beside_it(renv, settings):
    b = complete_job(renv, door="ok", photos=2, settings=settings)
    html = build(b, PHOTOS)
    names = re.findall(r'<img src="vayufile:([0-9a-f]{40})"', html)
    assert len(names) == 2 and set(names) == set(html.files)       # the bytes, not base64 text
    assert all(data[:3] == b"\xff\xd8\xff" for data in html.files.values())
    assert "data:image/jpeg" not in html and "display: grid" not in html
    pdf = render.render_pdf(html)                                  # the renderer asks for each by name
    pictures = [i for p in pypdf.PdfReader(io.BytesIO(pdf)).pages for i in p.images]
    assert len(pictures) == 2


def test_a_photo_shown_twice_is_fetched_and_kept_once(renv, settings):
    b = complete_job(renv, door="ok", photos=2, settings=settings)
    build(b, PHOTOS)                                               # the print copies exist now
    with mock.patch.object(storage, "read", wraps=storage.read) as read:
        html = build(b, PHOTOS, {**PHOTOS, "title": "Again"})
    assert html.count('<img src="vayufile:') == 4 and len(html.files) == 2
    assert sum(1 for c in read.call_args_list if str(c.args[0]).startswith("print/")) == 2


def grid_of(html):
    grid = html[html.index('<div class="photos'):]
    css = html[html.index("<style>"):html.index("</style>")]
    return grid[:grid.index("</table></div>")], css


def named(css, grid, style):
    """The class that carries `style`, used in the grid."""
    name = re.search(r"\.photos \.(s\d+)\{" + re.escape(style) + r"\}", css)
    assert name, style
    assert re.search(rf'class="(\w+ )*{name[1]}"', grid), style
    return name[1]


def test_a_photo_grid_is_a_table_of_fixed_cells(renv, settings):
    b = complete_job(renv, door="ok", photos=2, settings=settings)
    grid, css = grid_of(build(b, {**PHOTOS, "frame": {"gap": 4}}))
    assert grid.count("<tr>") == 1 and grid.count("<td") == 3      # 2 photos, 3 a row: 1 empty cell
    assert grid.count("<figure") == 2 and "<td class=" in grid and "style=" not in grid
    cell = (186 - 2 * 4) / 3                                       # A4 less the side margins, 2 gaps
    named(css, grid, f"width:{cell:.2f}mm;padding:0mm 4mm 0 0")
    named(css, grid, f"width:{cell:.2f}mm;padding:0mm 0mm 0 0")    # the row's last cell: no gap
    named(css, grid, f"width:{3 * round(cell, 2) + 8:.2f}mm")      # the table: exactly its cells
    one = named(css, grid, f"width:{cell:.2f}mm")                  # the figure, and the block itself
    assert grid.startswith(f'<div class="photos {one}">')
    assert ".photos table { table-layout: fixed" in css


def test_the_gap_between_rows_is_the_later_rows_top_padding(renv, settings):
    b = complete_job(renv, door="ok", photos=2, settings=settings)
    grid, css = grid_of(build(b, {**PHOTOS, "per_row": 1, "frame": {"gap": 6, "border": "grey"}}))
    assert grid.count("<tr>") == 2 and grid.count("<td") == 2
    named(css, grid, "width:186.00mm;padding:0mm 0mm 0 0")         # the first row
    named(css, grid, "width:186.00mm;padding:6mm 0mm 0 0")         # the second: the gap above it
    assert "border:0.3mm solid var(--line)" in css


def test_no_photos_is_an_empty_block():
    assert render._photos({"items": []}, 186, render.PRINT_EDGE, {}) == '<div class="photos"></div>'


def test_outside_a_report_the_pictures_are_data_uris(renv, settings):
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    media = source(b).answers["inspection"]["photo_a"]
    uris = render._print_uris([*media, "00000000-0000-0000-0000-000000000000"], render.PRINT_EDGE)
    assert (uris[0] or "").startswith("data:image/jpeg;base64,") and uris[1] is None


def test_the_fonts_are_handed_over_as_bytes_not_written_into_the_css(renv, settings):
    assert len(render.font_files()) == 6 and "base64" not in render.font_faces()
    assert all(f"url(vayufile:{name})" in render.font_faces() for name in render.font_files())
    b = complete_job(renv, door="ok", photos=1, settings=settings)
    pdf = render.render_pdf(build(b, {"type": "text", "html": "<p>Plain words 27-11 +91-94296</p>"}))
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    # copied or searched text is what was written (whole fonts broke the hyphen between digits)
    assert "Plain words 27-11 +91-94296" in "".join(p.extract_text() for p in reader.pages)
    fonts = {str(font.get_object()["/BaseFont"]) for page in reader.pages
             for font in page["/Resources"]["/Font"].values()}     # type: ignore[index,union-attr]
    assert any("Inter" in name for name in fonts), fonts           # our font, not a fallback


def test_a_name_we_did_not_hand_over_is_not_loaded():
    pdf = render.render_pdf('<html><body><img src="vayufile:nothing"><p>ok</p></body></html>')
    assert pdf[:4] == b"%PDF"
    assert not [i for p in pypdf.PdfReader(io.BytesIO(pdf)).pages for i in p.images]


def test_garbage_sweeps_pause_for_one_pdf_only():
    assert gc.isenabled()
    with render._no_sweeps():
        assert not gc.isenabled()
    assert gc.isenabled()
    gc.disable()
    try:
        with render._no_sweeps():                                  # was off: stays off
            pass
        assert not gc.isenabled()
    finally:
        gc.enable()

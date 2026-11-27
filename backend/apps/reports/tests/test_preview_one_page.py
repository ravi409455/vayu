"""The designer's quick preview: one template page drawn on its own (about 1 s, not the whole
report), still numbered as in the whole report; and the whole preview says which template page
each sheet belongs to."""
import base64
import io

import pypdf

from .test_reports import complete_job, renv, set_template, table  # noqa: F401

FOOT = {"normal": {"footer": {"height": 10, "right": [{"text": "Page {{ sys.page }} of {{ sys.pages }}"}]}}}


def three_pages():
    """Doors; a page that never shows for this booking; Odometer over two sheets."""
    return {"schema": 2, "paper": {"size": "A4"}, "bands": FOOT, "pages": [
        {"title": "Doors", "parts": [{**table([{"field": "inspection.door"}], title="Doors"), "id": "t1"}]},
        {"title": "Hidden", "show_if": {"==": [{"var": "inspection.door"}, "never"]},
         "parts": [{"type": "text", "html": "<p>Never shown</p>", "id": "x1"}]},
        {"title": "Odometer", "parts": [
            {**table([{"field": "inspection.odometer"}], title="Odometer"), "id": "t2"},
            {"type": "page_break"},
            {"type": "text", "html": "<p>Second sheet</p>", "id": "t3"}]}]}


def post(renv, settings, **extra):
    set_template(renv)
    b = complete_job(renv, settings=settings)
    draft = renv.admin.post(f"/api/v1/pdf-templates/{renv.template_id}/drafts").json()
    url = f"/api/v1/pdf-template-versions/{draft['id']}/preview"
    return lambda **more: renv.admin.post(
        url, {"booking": b["id"], "definition": three_pages(), **extra, **more}, format="json")


def words(body) -> list[str]:
    reader = pypdf.PdfReader(io.BytesIO(base64.b64decode(body["pdf"])))
    return [" ".join(p.extract_text().split()) for p in reader.pages]


def test_the_whole_preview_says_which_template_page_each_sheet_belongs_to(renv, settings):
    r = post(renv, settings)()
    assert r.status_code == 200, r.json()
    body = r.json()
    assert [s["section"] for s in body["pages"]] == [0, 2, 2]      # page 1 (hidden) has no sheet
    assert "Page 1 of 3" in words(body)[0] and "Page 3 of 3" in words(body)[2]


def test_one_template_page_is_drawn_on_its_own_with_the_reports_page_numbers(renv, settings):
    send = post(renv, settings)
    r = send(only_page=2, first_page=2, total_pages=3)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert [s["section"] for s in body["pages"]] == [2, 2]
    assert {p["id"] for s in body["pages"] for p in s["parts"]} == {"t2", "t3"}
    text = words(body)
    assert len(text) == 2 and "Doors" not in " ".join(text) and "Second sheet" in text[1]
    assert "Page 2 of 3" in text[0] and "Page 3 of 3" in text[1]   # as in the whole report
    alone = send(only_page=0).json()                               # no numbers given: its own
    assert [s["section"] for s in alone["pages"]] == [0] and "Page 1 of 1" in words(alone)[0]


def test_a_page_that_does_not_show_for_this_booking_gives_no_sheets(renv, settings):
    r = post(renv, settings)(only_page=1)
    assert r.status_code == 200 and r.json()["pages"] == [] and r.json()["pdf"] == ""
    assert r.json()["checks"] == [] and r.json()["filename"] == "SA37926.pdf"


def test_a_wrong_page_or_page_number_is_refused(renv, settings):
    send = post(renv, settings)
    for bad in ({"only_page": 3}, {"only_page": -1}, {"only_page": "0"}, {"only_page": True},
                {"only_page": 0, "first_page": 0, "total_pages": 3},
                {"only_page": 0, "first_page": 2}, {"only_page": 0, "first_page": 1, "total_pages": "3"}):
        r = send(**bad)
        assert r.status_code == 400 and r.json()["code"] == "INVALID_TEMPLATE", bad

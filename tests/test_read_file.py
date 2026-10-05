"""Reading a course file: what is fetched, what is refused, and how large.

The only tool that transfers a file rather than a JSON document, so the limits
are the interesting part.
"""

import io
import zipfile

import httpx2
import pytest

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.extract import MAX_SLIDES
from canvas_mcp.fixtures import build_pdf, demo_pdf
from canvas_mcp.sanitize import BEGIN, END
from canvas_mcp.server import build_client
from canvas_mcp.tools import build_tools
from canvas_mcp.tools.files import (
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    decode,
    is_text,
    make_read_file,
)

PDF = build_pdf("First page text", "Second page text")


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token-for-tests")


def serving(meta: dict, body: bytes = PDF, headers: dict | None = None) -> CanvasClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/download"):
            return httpx2.Response(200, content=body, headers=headers or {})
        return httpx2.Response(200, json=meta)

    return CanvasClient(transport=httpx2.MockTransport(handler))


READABLE = {
    "id": 7,
    "display_name": "lec01_intro.pdf",
    "content-type": "application/pdf",
    "url": "https://canvas.example.edu/files/7/download?verifier=FIXTUREx",
}


# --- reading --------------------------------------------------------------


def test_a_page_range_comes_back_attributed_and_bounded() -> None:
    with serving(READABLE) as client:
        result = make_read_file(client)(course_id=1, file_id=7, page_range="2")

    assert result["file"] == "lec01_intro.pdf"
    assert result["pages"] == "2-2 of 2"
    assert "Second page text" in result["text"]
    assert result["text"].startswith(BEGIN)
    assert result["text"].rstrip().endswith(END)


def test_the_download_link_never_reaches_the_output() -> None:
    """The url carries a verifier, which is an unauthenticated download link."""
    with serving(READABLE) as client:
        result = make_read_file(client)(course_id=1, file_id=7)
    assert "verifier" not in str(result)


def test_reading_a_file_works_end_to_end_in_demo_mode() -> None:
    result = build_tools(build_client(demo=True))["read_file"](
        course_id=1, file_id=15872029, page_range="1"
    )
    assert "Sorting is a comparison problem" in result["text"]
    assert result["pages"].endswith(f"of {len(demo_pdf().split(b'/Type /Page ')) - 1}")


# --- what is refused ------------------------------------------------------


@pytest.mark.parametrize("flag", ["hidden_for_user", "locked_for_user"])
def test_a_file_the_student_may_not_have_is_refused(flag: str) -> None:
    """For files, locked means the content is off limits — unlike an
    assignment, where it only means it cannot be submitted to."""
    with serving({**READABLE, flag: True}) as client:
        with pytest.raises(CanvasError, match="not available"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_refusal_says_what_to_do_instead() -> None:
    """The page-limit error names the limit and a way forward; this one used to
    stop at the diagnosis. Reported from a live session.

    The example used to be `SETUP.txt`, which this server now reads. An image
    is the thing it still cannot do anything with."""
    other = {**READABLE, "content-type": "image/png", "display_name": "plot.png"}
    with serving(other) as client:
        with pytest.raises(CanvasError, match="Open it in Canvas"):
            make_read_file(client)(course_id=1, file_id=7)


# --- text files -----------------------------------------------------------

# A LaTeX template is the case this exists for: source a model is asked to
# reason about and write alongside, where reformatting would lose the point.
TEMPLATE = (
    "\\documentclass{article}\n"
    "\\usepackage{amsmath}\n"
    "\\begin{document}\n"
    "\\section*{Homework week 5}\n"
    "% answer 1a here\n"
    "\\end{document}\n"
)

TEX = {
    "id": 8,
    "display_name": "template.tex",
    "content-type": "text/x-tex",
    "url": "https://canvas.example.edu/files/8/download?verifier=FIXTUREx",
}


def test_a_tex_file_comes_back_verbatim() -> None:
    """No markup stripping and no reflowing: the backslashes and the comment
    are the thing being asked about."""
    with serving(TEX, body=TEMPLATE.encode()) as client:
        result = make_read_file(client)(course_id=1, file_id=8)

    assert result["file"] == "template.tex"
    assert result["part"] == "1 of 1"
    assert "\\documentclass{article}" in result["text"]
    assert "% answer 1a here" in result["text"]
    assert result["text"].startswith(BEGIN)
    assert result["text"].rstrip().endswith(END)


def test_a_tex_file_canvas_refused_to_type_is_still_read() -> None:
    """Canvas types by extension and gives up often. This is the common case,
    not the exotic one."""
    vague = {**TEX, "content-type": "application/octet-stream"}
    with serving(vague, body=TEMPLATE.encode()) as client:
        result = make_read_file(client)(course_id=1, file_id=8)
    assert "\\documentclass{article}" in result["text"]


def test_an_untyped_binary_with_no_known_suffix_is_still_refused() -> None:
    """The name may overrule a vague type, not an absent reason to trust it."""
    blob = {**TEX, "content-type": "application/octet-stream", "display_name": "a.bin"}
    with serving(blob, body=b"\x00\x01") as client:
        with pytest.raises(CanvasError, match="Open it in Canvas"):
            make_read_file(client)(course_id=1, file_id=8)


def test_a_long_text_file_arrives_in_parts() -> None:
    body = ("% a line of a very long preamble\n" * 2000).encode()
    with serving(TEX, body=body) as client:
        first = make_read_file(client)(course_id=1, file_id=8)
        total = int(first["part"].split(" of ")[1])
        last = make_read_file(client)(course_id=1, file_id=8, part=total)

    assert total > 1
    assert "ask for part 2" in first["text"]
    assert "the last one" in last["text"]
    assert len(first["text"]) < MAX_TEXT_CHARS + 500


def test_a_part_of_a_text_file_that_does_not_exist_is_refused() -> None:
    with serving(TEX, body=TEMPLATE.encode()) as client:
        with pytest.raises(CanvasError, match="does not exist"):
            make_read_file(client)(course_id=1, file_id=8, part=4)


def test_the_download_link_never_reaches_a_text_answer() -> None:
    with serving(TEX, body=TEMPLATE.encode()) as client:
        result = make_read_file(client)(course_id=1, file_id=8)
    assert "verifier" not in str(result)


def test_text_that_is_not_utf8_is_read_rather_than_refused() -> None:
    """Canvas says nothing reliable about encoding, and latin-1 maps every
    byte, so a file written in one does not become an error."""
    assert decode("café".encode("latin-1")) == "caf\xe9"
    assert decode("café".encode()) == "café"


def test_a_byte_order_mark_does_not_become_a_character() -> None:
    assert decode("\ufeff\\documentclass".encode()) == "\\documentclass"


def test_is_text_prefers_the_type_and_falls_back_to_the_name() -> None:
    assert is_text("text/x-tex", "anything")
    assert is_text("text/plain", "notes")
    assert is_text("application/octet-stream", "template.tex")
    assert not is_text("application/pdf", "lecture.pdf")
    assert not is_text("image/png", "plot.png")
    assert not is_text("application/octet-stream", "archive.zip")


# --- zips -----------------------------------------------------------------

ZIP = {
    "id": 9,
    "display_name": "HW Week 5 - LaTeX template.zip",
    "content-type": "application/zip",
    "url": "https://canvas.example.edu/files/9/download?verifier=FIXTUREx",
}


def zipped(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in entries.items():
            archive.writestr(name, body)
    return buffer.getvalue()


TEMPLATE_ZIP = zipped(
    {
        "hw5/template.tex": TEMPLATE,
        "hw5/refs.bib": "@book{x, title={Y}}",
        "hw5/logo.png": b"\x89PNG",
    }
)


def test_a_zip_without_a_member_says_what_it_holds() -> None:
    """A model cannot guess `hw5/template.tex` from the outside. The listing is
    what replaces guessing."""
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        result = make_read_file(client)(course_id=1, file_id=9)

    assert result["file"] == "HW Week 5 - LaTeX template.zip"
    assert result["members"] == "3 of 3"
    names = [m["name"] for m in result["contains"]]
    assert names == ["hw5/template.tex", "hw5/refs.bib", "hw5/logo.png"]
    assert [m["readable"] for m in result["contains"]] == [True, True, False]
    assert result["contains"][0]["size"] == len(TEMPLATE)


def test_a_named_member_comes_back_as_text() -> None:
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        result = make_read_file(client)(
            course_id=1, file_id=9, member="hw5/template.tex"
        )

    assert result["member"] == "hw5/template.tex"
    assert result["part"] == "1 of 1"
    assert "\\documentclass{article}" in result["text"]
    assert "% answer 1a here" in result["text"]
    assert result["text"].startswith(BEGIN)


def test_the_attribution_names_the_archive_and_the_member() -> None:
    """Which file inside which archive — a model quoting this should be able to
    say where it came from."""
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        result = make_read_file(client)(
            course_id=1, file_id=9, member="hw5/template.tex"
        )
    assert "HW Week 5 - LaTeX template.zip:hw5/template.tex" in result["text"]


def test_a_member_this_server_cannot_read_is_refused_by_name() -> None:
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        with pytest.raises(CanvasError, match="only text out of an archive"):
            make_read_file(client)(course_id=1, file_id=9, member="hw5/logo.png")


def test_a_nested_zip_is_listed_and_not_opened() -> None:
    """One archive is a convenience; a chain of them is a way to spend
    memory."""
    nested = zipped({"inner.zip": TEMPLATE_ZIP})
    with serving(ZIP, body=nested) as client:
        listing = make_read_file(client)(course_id=1, file_id=9)
        assert listing["contains"] == [
            {"name": "inner.zip", "size": len(TEMPLATE_ZIP), "readable": False}
        ]
        with pytest.raises(CanvasError, match="only text out of an archive"):
            make_read_file(client)(course_id=1, file_id=9, member="inner.zip")


def test_a_member_that_is_not_there_is_refused_with_a_way_forward() -> None:
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        with pytest.raises(CanvasError, match="without a member to see"):
            make_read_file(client)(course_id=1, file_id=9, member="hw5/nope.tex")


def test_a_zip_canvas_refused_to_type_is_still_looked_into() -> None:
    vague = {**ZIP, "content-type": "application/octet-stream"}
    with serving(vague, body=TEMPLATE_ZIP) as client:
        assert make_read_file(client)(course_id=1, file_id=9)["members"] == "3 of 3"


def test_something_that_is_not_a_zip_is_refused_in_words() -> None:
    with serving(ZIP, body=b"not a zip at all") as client:
        with pytest.raises(CanvasError, match="not a readable zip"):
            make_read_file(client)(course_id=1, file_id=9)


def test_the_download_link_never_reaches_a_zip_answer() -> None:
    with serving(ZIP, body=TEMPLATE_ZIP) as client:
        listing = make_read_file(client)(course_id=1, file_id=9)
        content = make_read_file(client)(
            course_id=1, file_id=9, member="hw5/template.tex"
        )
    assert "verifier" not in str(listing)
    assert "verifier" not in str(content)


def test_a_file_that_cannot_be_read_is_named_rather_than_failing() -> None:
    """The example was `code.zip` until this server learned to look inside one.
    A Word document is the thing it still only has a name for."""
    other = {
        **READABLE,
        "content-type": "application/vnd.openxmlformats-officedocument"
        ".wordprocessingml.document",
        "display_name": "notes.docx",
    }
    with serving(other) as client:
        with pytest.raises(CanvasError, match="notes.docx is application/vnd"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_file_with_no_download_link_says_what_that_usually_means() -> None:
    with serving({k: v for k, v in READABLE.items() if k != "url"}) as client:
        with pytest.raises(CanvasError, match="no download link"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_scan_is_refused_with_the_reason_not_returned_blank() -> None:
    with serving(READABLE, body=build_pdf("", "")) as client:
        with pytest.raises(CanvasError, match="OCR"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_page_range_that_cannot_work_keeps_its_explanation() -> None:
    with serving(READABLE) as client:
        with pytest.raises(CanvasError, match="does not exist"):
            make_read_file(client)(course_id=1, file_id=7, page_range="9")


# --- size -----------------------------------------------------------------


def test_a_large_file_is_refused_before_it_is_transferred() -> None:
    headers = {"content-length": str(MAX_FILE_BYTES + 1)}
    with serving(READABLE, headers=headers) as client:
        with pytest.raises(CanvasError, match="over the"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_server_understating_its_size_is_still_stopped() -> None:
    """Content-Length is a claim, not a promise."""
    body = b"%PDF-1.4\n" + b"x" * (MAX_FILE_BYTES + 10)
    with serving(READABLE, body=body, headers={"content-length": "10"}) as client:
        with pytest.raises(CanvasError, match="over the"):
            make_read_file(client)(course_id=1, file_id=7)


# --- how a file is actually served ----------------------------------------


def test_the_redirect_canvas_serves_files_behind_is_followed() -> None:
    """Canvas answers a file URL with a redirect to a signed location. Without
    following it the body is empty and the failure surfaces much later, as
    "not a readable PDF" about a file that is fine."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.host)
        if request.url.path.endswith("/download"):
            return httpx2.Response(
                302, headers={"location": "https://cdn.example.edu/signed/x.pdf"}
            )
        if request.url.host == "cdn.example.edu":
            return httpx2.Response(200, content=PDF)
        return httpx2.Response(200, json=READABLE)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        result = make_read_file(client)(course_id=1, file_id=7, page_range="1")

    assert "First page text" in result["text"]
    assert "cdn.example.edu" in seen


def test_the_token_does_not_follow_a_file_to_another_host() -> None:
    """The signed location needs no credential and should not receive one."""
    headers_seen: dict[str, dict] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        headers_seen[request.url.host] = dict(request.headers)
        if request.url.path.endswith("/download"):
            return httpx2.Response(
                302, headers={"location": "https://cdn.example.edu/signed/x.pdf"}
            )
        if request.url.host == "cdn.example.edu":
            return httpx2.Response(200, content=PDF)
        return httpx2.Response(200, json=READABLE)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        make_read_file(client)(course_id=1, file_id=7, page_range="1")

    assert "authorization" in headers_seen["canvas.example.edu"]
    assert "authorization" not in headers_seen["cdn.example.edu"]


def test_a_failed_download_names_the_path_and_not_the_verifier() -> None:
    """A Canvas file URL carries a verifier, which is an unauthenticated
    download link — section 5 keeps those out of anything a caller sees."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/download"):
            return httpx2.Response(403)
        return httpx2.Response(200, json=READABLE)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(CanvasError) as excinfo:
            make_read_file(client)(course_id=1, file_id=7)

    message = str(excinfo.value)
    assert "/files/7/download" in message
    assert "verifier" not in message


# --- build-up frames, through the tool ------------------------------------


def build_up_deck() -> bytes:
    """Four slides written the way LaTeX writes them: one page per \\pause."""
    return build_pdf(
        "Collections. A list keeps order.",
        "Collections. A list keeps order. A set does not.",
        "Collections. A list keeps order. A set does not. A map has keys.",
        "Complexity. Constant time is best.",
        "Complexity. Constant time is best. Linear is next.",
    )


def test_the_reply_says_how_many_slides_a_range_held() -> None:
    """Five pages, two slides — the count is what tells a caller whether the
    range was worth the call."""
    with serving(READABLE, body=build_up_deck()) as client:
        result = make_read_file(client)(course_id=1, file_id=7)

    assert result["pages"] == "1-5 of 5"
    assert result["entries"] == 2
    assert "build-up frames of one slide" in result["text"]
    assert "A map has keys" in result["text"]


def test_too_many_slides_are_cut_with_a_way_forward() -> None:
    """Collapsing bounds the output, but a range of genuinely distinct slides
    still has to stop somewhere."""
    distinct = build_pdf(*(f"Slide {i}. Something about topic {i}." for i in range(25)))
    with serving(READABLE, body=distinct) as client:
        result = make_read_file(client)(course_id=1, file_id=7)

    assert result["entries"] == MAX_SLIDES
    assert "Ask for a narrower range" in result["text"]


def test_the_count_is_a_number_and_counts_what_it_says() -> None:
    """It was "4 of 4 in that range", which read as though something had been
    cut when nothing had. It is now a number, and named for what it counts:
    entries returned, not slides in the document — a field called "slides"
    reported 12 for four slides the day the extractor changed under it."""
    with serving(READABLE, body=build_up_deck()) as client:
        result = make_read_file(client)(course_id=1, file_id=7)
    assert isinstance(result["entries"], int)
    assert "slides" not in result

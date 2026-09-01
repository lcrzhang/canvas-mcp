"""Reading a course file: what is fetched, what is refused, and how large.

The only tool that transfers a file rather than a JSON document, so the limits
are the interesting part.
"""

import httpx2
import pytest

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.extract import MAX_SLIDES
from canvas_mcp.fixtures import build_pdf, demo_pdf
from canvas_mcp.sanitize import BEGIN, END
from canvas_mcp.server import build_client
from canvas_mcp.tools import build_tools
from canvas_mcp.tools.files import MAX_FILE_BYTES, make_read_file

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
    stop at the diagnosis. Reported from a live session."""
    other = {**READABLE, "content-type": "text/plain", "display_name": "SETUP.txt"}
    with serving(other) as client:
        with pytest.raises(CanvasError, match="Open it in Canvas"):
            make_read_file(client)(course_id=1, file_id=7)


def test_a_file_that_is_not_a_pdf_is_named_rather_than_failing() -> None:
    other = {**READABLE, "content-type": "application/zip", "display_name": "code.zip"}
    with serving(other) as client:
        with pytest.raises(CanvasError, match="code.zip is application/zip"):
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

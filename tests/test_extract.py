"""Text extraction, against PDFs built here rather than captured.

Nothing is downloaded and no real document is committed: the tests assemble a
minimal PDF whose text they already know, which proves more than a captured
file would and keeps a teacher's slides out of the repository.
"""

import pytest

from canvas_mcp.extract import (
    MAX_PAGES,
    ExtractionError,
    extract_text,
    page_count,
    parse_page_range,
)


def make_pdf(*page_texts: str) -> bytes:
    """A valid PDF with one text line per page. An empty string gives a page
    with no text layer, which is what a scan looks like from here."""
    pages = len(page_texts)
    page_ids = [3 + 2 * i for i in range(pages)]
    content_ids = [4 + 2 * i for i in range(pages)]
    font_id = 3 + 2 * pages

    objects: list[tuple[int, bytes]] = [(1, b"<< /Type /Catalog /Pages 2 0 R >>")]
    kids = b" ".join(f"{i} 0 R".encode() for i in page_ids)
    objects.append((2, b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % pages))
    for index, text in enumerate(page_texts):
        objects.append(
            (
                page_ids[index],
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
                f"/Contents {content_ids[index]} 0 R /Resources << /Font << "
                f"/F1 {font_id} 0 R >> >> >>".encode(),
            )
        )
        stream = f"BT /F1 12 Tf 20 150 Td ({text}) Tj ET".encode() if text else b""
        objects.append(
            (
                content_ids[index],
                b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            )
        )
    objects.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number, body in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    start = len(out)
    size = max(offsets) + 1
    out += b"xref\n0 %d \n" % size + b"0000000000 65535 f \n"
    for number in range(1, size):
        out += b"%010d 00000 n \n" % offsets.get(number, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        size,
        start,
    )
    return bytes(out)


TWO_PAGES = make_pdf("Sorting is comparison based", "Quicksort picks a pivot")


# --- reading --------------------------------------------------------------


def test_a_page_count_is_reported() -> None:
    assert page_count(TWO_PAGES) == 2


def test_text_comes_back_with_the_page_it_was_on() -> None:
    """A model quoting a passage should be able to say which page it is on."""
    text = extract_text(TWO_PAGES, [0, 1])
    assert "[page 1]" in text and "[page 2]" in text
    assert "Sorting is comparison based" in text
    assert "Quicksort picks a pivot" in text


def test_only_the_pages_asked_for_are_read() -> None:
    text = extract_text(TWO_PAGES, [1])
    assert "Quicksort" in text
    assert "Sorting is comparison" not in text


def test_a_document_with_no_text_layer_is_refused_with_a_reason() -> None:
    """SCOPE section 7 rules out OCR, so silence would read as "blank page"
    about a page that is full of scanned writing."""
    with pytest.raises(ExtractionError, match="OCR"):
        extract_text(make_pdf("", ""), [0, 1])


def test_a_page_without_text_beside_one_with_it_is_marked_not_dropped() -> None:
    mixed = make_pdf("Readable", "")
    text = extract_text(mixed, [0, 1])
    assert "Readable" in text
    assert "[page 2] no text" in text


def test_something_that_is_not_a_pdf_says_so() -> None:
    with pytest.raises(ExtractionError, match="not a readable PDF"):
        extract_text(b"this is a text file", [0])


# --- page ranges ----------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("1", [0]),
        ("3", [2]),
        ("2-4", [1, 2, 3]),
        (" 2 - 3 ", [1, 2]),
        (None, [0, 1, 2, 3, 4]),
        ("", [0, 1, 2, 3, 4]),
    ],
)
def test_page_ranges_are_one_based_and_inclusive(
    given: str | None, expected: list[int]
) -> None:
    """One-based because that is what is printed on the page."""
    assert parse_page_range(given, total=5) == expected


def test_a_range_running_past_the_end_stops_at_the_end() -> None:
    assert parse_page_range("4-99", total=5) == [3, 4]


@pytest.mark.parametrize(
    ("given", "says"),
    [
        ("ten", "page range"),
        ("5-2", "ends before it begins"),
        ("0-2", "counted from 1"),
        ("9-9", "does not exist"),
    ],
)
def test_a_range_that_cannot_work_says_why(given: str, says: str) -> None:
    with pytest.raises(ExtractionError, match=says):
        parse_page_range(given, total=5)


def test_asking_for_a_whole_document_is_refused() -> None:
    with pytest.raises(ExtractionError, match=str(MAX_PAGES)):
        parse_page_range(f"1-{MAX_PAGES + 1}", total=200)

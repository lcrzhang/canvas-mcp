"""Text extraction, against PDFs built here rather than captured.

Nothing is downloaded and no real document is committed: the tests assemble a
minimal PDF whose text is written next to the assertion, which proves more
than a captured file would and keeps a teacher's slides out of the repository.
Demo mode uses the same builder.
"""

import pytest

from canvas_mcp.extract import (
    MAX_PAGES,
    ExtractionError,
    extract_text,
    page_count,
    parse_page_range,
)
from canvas_mcp.fixtures import build_pdf

TWO_PAGES = build_pdf("Sorting is comparison based", "Quicksort picks a pivot")


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
        extract_text(build_pdf("", ""), [0, 1])


def test_a_page_without_text_beside_one_with_it_is_marked_not_dropped() -> None:
    mixed = build_pdf("Readable", "")
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

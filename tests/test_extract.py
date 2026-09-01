"""Text extraction, against PDFs built here rather than captured.

Nothing is downloaded and no real document is committed: the tests assemble a
minimal PDF whose text is written next to the assertion, which proves more
than a captured file would and keeps a teacher's slides out of the repository.
Demo mode uses the same builder.
"""

import pytest

from canvas_mcp.extract import (
    DEFAULT_EXTRACTOR,
    EXTRACTORS,
    MAX_PAGES,
    ExtractionError,
    collapse_overlays,
    extract_slides,
    extract_text,
    format_slides,
    is_the_same_slide,
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


# --- build-up frames ------------------------------------------------------
#
# A lecture deck has one page per \pause, so 94 pages can be 30 slides. These
# pin when two pages count as one slide and, more importantly, when they do
# not.

TITLE = "Asymptotic bounds"


def frame(*lines: str) -> str:
    return "\n".join((TITLE, *lines))


def test_identical_consecutive_pages_become_one_slide() -> None:
    pages = [
        (0, frame("Big-O is an upper bound")),
        (1, frame("Big-O is an upper bound")),
    ]
    assert collapse_overlays(pages) == [([0, 1], frame("Big-O is an upper bound"))]


def test_a_build_up_keeps_the_fullest_frame() -> None:
    """With \\pause the last frame is the fullest. With \\only it is not, so the
    longest is kept rather than the last."""
    pages = [
        (0, frame("Big-O")),
        (1, frame("Big-O", "Omega")),
        (2, frame("Big-O", "Omega", "Theta")),
    ]
    ((indexes, text),) = collapse_overlays(pages)
    assert indexes == [0, 1, 2]
    assert "Theta" in text


def test_content_that_disappears_is_not_collapsed_away() -> None:
    """`\\only<1>{X}` shows X on the first frame and not after. Neither page
    contains the other, so both are kept rather than one being chosen."""
    pages = [(0, frame("Only on the first")), (1, frame("Only on the second"))]
    assert len(collapse_overlays(pages)) == 2


def test_two_slides_are_kept_apart_even_when_one_is_a_subset() -> None:
    """A short slide's words can be contained in a longer one by chance. The
    opening has to match too, and different slides open differently."""
    pages = [(0, "Sorting\nquick merge"), (1, "Searching\nquick merge binary")]
    assert len(collapse_overlays(pages)) == 2


def test_a_run_is_labelled_with_the_pages_it_came_from() -> None:
    """A model quoting a slide should be able to say where it is."""
    pages = [(43, frame("a")), (44, frame("a")), (45, frame("a")), (46, "Other\nb")]
    text = format_slides(collapse_overlays(pages))
    assert "[pages 44-46, 3 build-up frames of one slide]" in text
    assert "[page 47]" in text


def test_a_lone_page_is_not_called_a_build_up() -> None:
    assert "build-up" not in format_slides(collapse_overlays([(0, frame("a"))]))


def test_the_opening_is_compared_whatever_the_line_breaks() -> None:
    """Whether a title lands on its own line depends on the extractor, so the
    comparison uses a prefix rather than the first line."""
    assert is_the_same_slide("Asymptotic bounds Big-O", "Asymptotic bounds Big-O Omega")


def test_a_deck_of_build_ups_collapses_end_to_end() -> None:
    deck = build_pdf(
        "Collections. A list keeps order.",
        "Collections. A list keeps order. A set does not.",
        "Collections. A list keeps order. A set does not. A map has keys.",
        "Complexity. Constant time is best.",
    )
    slides = extract_slides(deck, range(4))
    assert len(slides) == 2
    assert "A map has keys" in slides[0][1]


def test_an_unreadable_page_is_never_folded_into_its_neighbour() -> None:
    """A page with no text is not a build-up frame — it is a page that could
    not be read. A full-page scanned diagram would otherwise vanish into the
    slide before it."""
    pages = [(0, frame("Readable")), (1, "")]
    assert len(collapse_overlays(pages)) == 2


# --- two backends, on purpose and temporarily -----------------------------


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_both_backends_read_the_same_document(extractor: str) -> None:
    deck = build_pdf("Sorting is comparison based", "Quicksort picks a pivot")
    slides = extract_slides(deck, [0, 1], extractor=extractor)
    text = format_slides(slides)
    assert "Sorting is comparison based" in text
    assert "Quicksort picks a pivot" in text


@pytest.mark.parametrize("extractor", sorted(EXTRACTORS))
def test_both_backends_refuse_something_that_is_not_a_pdf(extractor: str) -> None:
    """A backend swap must not change which failures are explained."""
    with pytest.raises(ExtractionError, match="not a readable PDF"):
        extract_slides(b"this is a text file", [0], extractor=extractor)


def test_an_unknown_backend_names_the_ones_there_are() -> None:
    with pytest.raises(ExtractionError, match="pdfplumber, pypdf"):
        extract_slides(build_pdf("x"), [0], extractor="pymupdf")


def test_the_default_is_the_backend_with_evidence_behind_it() -> None:
    """pdfplumber is expected to do better and has not been measured. Making it
    the default on that expectation is the mistake this project has already
    made twice."""
    assert DEFAULT_EXTRACTOR == "pypdf"

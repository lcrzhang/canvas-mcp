"""Pull readable text out of a PDF.

Everything that knows about PDFs lives here, behind one function. `SCOPE.md`
section 7 rules out OCR, so a page with no text layer is refused with an
explanation rather than returned as an empty string — silence would read as
"this page is blank", which is a plausible wrong answer about a page that is
full of scanned writing.
"""

import io
import re
from collections.abc import Iterable

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# A page range a person would write: "12" or "10-15", one-based and inclusive.
_RANGE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")

# Physical pages read in one call. Generous because a slide deck spends most of
# them on build-up frames: 94 physical pages is a normal 30-slide lecture.
MAX_PAGES = 60

# Slides returned after those frames are collapsed. This is the limit that
# means what the old page limit was trying to mean — a passage, not a document.
MAX_SLIDES = 20


class ExtractionError(Exception):
    """Raised when a document cannot be read, with the reason a person needs."""


def parse_page_range(page_range: str | None, total: int) -> list[int]:
    """Turn "10-15" into the zero-based page indexes it names.

    One-based and inclusive, because that is what is printed on the page and
    what a student will type. Returns every page when nothing is asked for.
    """
    if page_range is None or not page_range.strip():
        wanted = list(range(total))
    else:
        match = _RANGE.match(page_range)
        if not match:
            raise ExtractionError(
                f"Could not read {page_range!r} as a page range. Write a single "
                'page ("12") or a span ("10-15"), counting from 1.'
            )
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1:
            raise ExtractionError("Pages are counted from 1.")
        if last < first:
            raise ExtractionError(f"{page_range!r} ends before it begins.")
        if first > total:
            raise ExtractionError(
                f"This document has {total} pages, so page {first} does not exist."
            )
        wanted = list(range(first - 1, min(last, total)))

    if len(wanted) > MAX_PAGES:
        raise ExtractionError(
            f"That is {len(wanted)} pages. Ask for at most {MAX_PAGES} at a "
            "time. Slide decks repeat each slide once per build-up frame, so "
            f"{MAX_PAGES} pages is often far fewer than {MAX_PAGES} slides."
        )
    return wanted


def page_count(data: bytes) -> int:
    return len(_read(data).pages)


def _words(text: str) -> set[str]:
    return set(text.split())


# How much of the opening has to match for two pages to be the same slide. A
# frame title and the first words under it, roughly.
OPENING = 40


def _opening(text: str) -> str:
    """The start of a page, with whitespace flattened.

    Compared instead of the first line, because whether a title lands on a line
    of its own depends on how the extractor breaks the text — and a heuristic
    that only works when it does would fail silently on the decks where it
    does not.
    """
    return " ".join(text.split())[:OPENING]


def is_the_same_slide(earlier: str, later: str) -> bool:
    """Whether two consecutive pages are frames of one slide.

    LaTeX beamer writes every `\\pause` as its own page, so a lecture deck has
    several near-identical pages per slide. Two pages count as one slide when
    they open with the same text and one's words are contained in the
    other's.

    Containment in either direction, because content can disappear as well as
    appear: `\\only<1>{...}` shows something on the first frame and not after.
    Requiring the same opening is what keeps two genuinely different slides
    apart when one happens to use a subset of the other's words.

    Deliberately not based on the slide number in a footer. That number exists
    in one beamer theme and not in others, and a regex that misfires would
    merge unrelated slides — silently, which is the wrong direction to fail in.
    """
    if not earlier.strip() or not later.strip():
        # A page with no text is not a frame of anything: it is a page that
        # could not be read, which is worth saying rather than folding into a
        # neighbour. A full-page scanned diagram would otherwise disappear.
        return False

    first_opening, second_opening = _opening(earlier), _opening(later)
    # A prefix rather than an exact match: on a short slide the words a frame
    # adds still fall inside the first OPENING characters, so requiring
    # equality would keep every build-up apart.
    if not (
        first_opening.startswith(second_opening)
        or second_opening.startswith(first_opening)
    ):
        return False
    first, second = _words(earlier), _words(later)
    return first <= second or second <= first


def collapse_overlays(pages: list[tuple[int, str]]) -> list[tuple[list[int], str]]:
    """Group build-up frames into slides, keeping the fullest frame of each.

    The fullest rather than the last: with `\\pause` the last frame is the
    fullest, but with `\\only` it is not, and taking the last would drop text
    that appeared on an earlier one.
    """
    slides: list[tuple[list[int], str]] = []
    for index, text in pages:
        if slides and is_the_same_slide(slides[-1][1], text):
            indexes, kept = slides[-1]
            slides[-1] = (indexes + [index], max(kept, text, key=len))
        else:
            slides.append(([index], text))
    return slides


def extract_slides(data: bytes, pages: Iterable[int]) -> list[tuple[list[int], str]]:
    """The pages asked for, with build-up frames collapsed into slides."""
    reader = _read(data)
    wanted = list(pages)

    extracted = [
        (index, (reader.pages[index].extract_text() or "").strip()) for index in wanted
    ]

    if not any(text for _, text in extracted):
        raise ExtractionError(
            f"No text on {_describe(wanted)}. The page is probably a scan or an "
            "image: this server does not do OCR, so there is nothing to read. "
            "Try another page range, or open the file in Canvas."
        )
    return collapse_overlays(extracted)


def format_slides(slides: list[tuple[list[int], str]]) -> str:
    """Label each slide with the pages it came from, so a model can cite it."""
    parts = []
    for indexes, text in slides:
        if len(indexes) == 1:
            label = f"[page {indexes[0] + 1}]"
        else:
            label = (
                f"[pages {indexes[0] + 1}-{indexes[-1] + 1}, "
                f"{len(indexes)} build-up frames of one slide]"
            )
        parts.append(f"{label}\n{text}" if text else f"{label} no text")
    return "\n\n".join(parts)


def extract_text(data: bytes, pages: Iterable[int]) -> str:
    """The only function that knows what a PDF is.

    Swapping the backend means replacing this and `page_count`, and nothing
    else in the project needs to hear about it.
    """
    return format_slides(extract_slides(data, pages))


def _read(data: bytes) -> PdfReader:
    try:
        return PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise ExtractionError(f"This file is not a readable PDF: {exc}") from exc


def _describe(pages: list[int]) -> str:
    if len(pages) == 1:
        return f"page {pages[0] + 1}"
    return f"pages {pages[0] + 1}-{pages[-1] + 1}"

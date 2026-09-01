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

# Reading more than this at once is a request for a whole document rather than
# a passage, and the answer would be truncated anyway.
MAX_PAGES = 20


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
            "time, so the answer is about a passage rather than a document."
        )
    return wanted


def page_count(data: bytes) -> int:
    return len(_read(data).pages)


def extract_text(data: bytes, pages: Iterable[int]) -> str:
    """The only function that knows what a PDF is.

    Swapping the backend means replacing this and `page_count`, and nothing
    else in the project needs to hear about it.
    """
    reader = _read(data)
    wanted = list(pages)

    extracted = []
    for index in wanted:
        text = reader.pages[index].extract_text() or ""
        extracted.append((index, text.strip()))

    if not any(text for _, text in extracted):
        raise ExtractionError(
            f"No text on {_describe(wanted)}. The page is probably a scan or an "
            "image: this server does not do OCR, so there is nothing to read. "
            "Try another page range, or open the file in Canvas."
        )

    return "\n\n".join(
        f"[page {index + 1}]\n{text}" if text else f"[page {index + 1}] no text"
        for index, text in extracted
    )


def _read(data: bytes) -> PdfReader:
    try:
        return PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise ExtractionError(f"This file is not a readable PDF: {exc}") from exc


def _describe(pages: list[int]) -> str:
    if len(pages) == 1:
        return f"page {pages[0] + 1}"
    return f"pages {pages[0] + 1}-{pages[-1] + 1}"

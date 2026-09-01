"""The `list_courses` tool."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import slim_course

COURSES_PARAMS: dict[str, Any] = {
    "enrollment_state": "active",
    # Without this the response carries enrollment_term_id and nothing else;
    # a bare 417 tells a model nothing.
    "include[]": ["term"],
}


def term_has_ended(course: dict[str, Any], now: datetime) -> bool:
    """Whether the course's term is over.

    `enrollment_state=active` means the *enrolment* is active, not that the
    term is running: Canvas keeps returning courses from terms that finished
    years ago. A term with no end date counts as current — an open-ended term
    is a real thing, and guessing it is over would hide a course.
    """
    end_at = (course.get("term") or {}).get("end_at")
    if not end_at:
        return False
    try:
        return datetime.fromisoformat(end_at) < now
    except ValueError:
        # An unparseable date is not grounds for hiding a course.
        return False


def make_list_courses(client: CanvasClient) -> Callable[..., list[dict[str, Any]]]:
    """Build the tool, with the client closed over rather than passed in."""

    def list_courses(
        term_filter: str | None = None,
        current_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Which courses the student is enrolled in, with their ids.

        Start here. Every other Canvas tool needs a course id, and this is the
        only way to get one. Returns id, name, course code and term name.

        Only courses whose term is still running are returned. Canvas keeps an
        enrolment active for years after a term ends, so the unfiltered list
        mixes this semester with 2024 — pass current_only=false when the
        student asks about a course they finished.

        term_filter matches part of a term name, case-insensitively: "semester
        1" or "2026". It filters what is already returned, so combine it with
        current_only=false to reach a past term.
        """
        raw = list(client.paginate("/courses", params=COURSES_PARAMS))
        if current_only:
            now = datetime.now(UTC)
            raw = [course for course in raw if not term_has_ended(course, now)]
        courses = [slim_course(course) for course in raw]
        if term_filter is None:
            return courses
        wanted = term_filter.casefold()
        return [
            course
            for course in courses
            if course["term"] and wanted in course["term"].casefold()
        ]

    return list_courses

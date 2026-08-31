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
        """List the courses the student is enrolled in.

        Returns the course id, name, course code and term name. The id is what
        every other Canvas tool needs, so this is usually the first call.

        By default only courses whose term is still running are returned.
        Canvas keeps an enrolment active long after a term ends, so without
        this the list mixes this year's courses with ones from years ago. Pass
        current_only=false to see everything, including finished terms.

        Optionally filter by term name, for example "Semester 1" — matching is
        case-insensitive and partial.
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

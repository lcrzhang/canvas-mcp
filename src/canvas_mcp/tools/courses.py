"""The `list_courses` tool."""

from collections.abc import Callable
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import slim_course

COURSES_PARAMS: dict[str, Any] = {
    "enrollment_state": "active",
    # Without this the response carries enrollment_term_id and nothing else;
    # a bare 417 tells a model nothing.
    "include[]": ["term"],
}


def make_list_courses(client: CanvasClient) -> Callable[..., list[dict[str, Any]]]:
    """Build the tool, with the client closed over rather than passed in."""

    def list_courses(term_filter: str | None = None) -> list[dict[str, Any]]:
        """List the courses the student is currently enrolled in.

        Returns the course id, name, course code and term name for every
        active enrolment. The id is what every other Canvas tool needs, so
        this is usually the first call. Optionally filter by term name, for
        example "Semester 1" — matching is case-insensitive and partial.
        """
        courses = [
            slim_course(course)
            for course in client.paginate("/courses", params=COURSES_PARAMS)
        ]
        if term_filter is None:
            return courses
        wanted = term_filter.casefold()
        return [
            course
            for course in courses
            if course["term"] and wanted in course["term"].casefold()
        ]

    return list_courses

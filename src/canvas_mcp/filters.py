"""Turn a raw Canvas response into the narrow dict a tool returns.

These filters are **allowlists**: the output is built from named fields rather
than by removing dangerous ones. A denylist has to be complete to be correct,
and the raw `/courses` response carries LTI and admin plumbing nobody predicted
— see `SCOPE.md` section 5, and the capture on 2026-08-30 that confirmed it.

An allowlist is wrong in the safe direction: a field nobody thought of comes
out missing rather than leaked.
"""

from typing import Any

# The complete output of slim_course(). Tests assert this exactly, so widening
# it is a deliberate act with a failing test attached.
COURSE_FIELDS = ("id", "name", "course_code", "term")


def slim_course(course: dict[str, Any]) -> dict[str, Any]:
    """Reduce one raw course object to what a model needs.

    `term` is None when the response was fetched without `include[]=term`.
    A bare `enrollment_term_id` is not used as a fallback: `417` tells a model
    nothing, and a plausible-looking wrong answer is worse than a missing one.

    Missing fields become None rather than raising. One malformed course should
    not fail a whole listing in a read-only tool.
    """
    term = course.get("term") or {}
    return {
        "id": course.get("id"),
        "name": course.get("name"),
        "course_code": course.get("course_code"),
        "term": term.get("name"),
    }

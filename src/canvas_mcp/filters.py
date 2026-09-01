"""Turn a raw Canvas response into the narrow dict a tool returns.

These filters are **allowlists**: the output is built from named fields rather
than by removing dangerous ones. A denylist has to be complete to be correct,
and the raw `/courses` response carries LTI and admin plumbing nobody predicted
— see `SCOPE.md` section 5, and the capture on 2026-08-30 that confirmed it.

An allowlist is wrong in the safe direction: a field nobody thought of comes
out missing rather than leaked.
"""

from typing import Any

from canvas_mcp.sanitize import sanitize

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


# The complete output of slim_submission(). Everything else in a submission
# stays behind: 129 fields arrive, including secure_params, preview_url,
# submissions_download_url and the assignment's full HTML description.
SUBMISSION_FIELDS = (
    "assignment",
    "score",
    "points_possible",
    "grade",
    "status",
    "flags",
)

# Reported only when true. Three booleans that are usually false are three
# fields of noise; a list names what is actually the case.
SUBMISSION_FLAGS = ("late", "missing", "excused")


def slim_submission(submission: dict[str, Any]) -> dict[str, Any]:
    """Reduce one raw submission to a score a student would recognise.

    `assignment` is the assignment's name, which is only present when the
    request used `include[]=assignment`; without it there is no way to tell
    which assignment a score belongs to, so it comes back None rather than as
    a bare id.

    The assignment's `description` is written by a teacher and is untrusted
    content (`SCOPE.md` section 6). The allowlist leaves it out, which is the
    kind of field a denylist forgets.
    """
    assignment = submission.get("assignment") or {}
    return {
        "assignment": assignment.get("name"),
        "score": submission.get("score"),
        "points_possible": assignment.get("points_possible"),
        "grade": submission.get("grade"),
        "status": submission.get("workflow_state"),
        "flags": [flag for flag in SUBMISSION_FLAGS if submission.get(flag)],
    }


# The complete output of slim_assignment(). 129 fields arrive, including the
# assignment's HTML description, the student's own submitted body and url,
# secure_params and every moderation setting the course has.
ASSIGNMENT_FIELDS = ("id", "name", "due_at", "points", "submitted", "locked")


def slim_assignment(assignment: dict[str, Any]) -> dict[str, Any]:
    """Reduce one raw assignment to what a student needs to plan.

    `submitted` comes from the nested submission, which is only present when
    the request used `include[]=submission`; without it nothing is known, so it
    is None rather than False. Claiming "not submitted" on missing information
    is exactly the plausible wrong answer this project tries not to produce.

    `locked` is reported rather than used to hide the assignment. See
    `SCOPE.md` section 5 and the note in `ROADMAP.md` step 6: a locked
    assignment is one you cannot submit to right now, not one you may not know
    about.
    """
    submission = assignment.get("submission")
    return {
        "id": assignment.get("id"),
        "name": assignment.get("name"),
        "due_at": assignment.get("due_at"),
        "points": assignment.get("points_possible"),
        "submitted": bool(submission.get("submitted_at")) if submission else None,
        "locked": bool(assignment.get("locked_for_user")),
    }


# slim_assignment plus the one field that needs sanitizing. Kept as a separate
# function rather than a flag: the list view must never carry a description,
# and a boolean parameter is easier to get wrong than two names.
ASSIGNMENT_DETAIL_FIELDS = (*ASSIGNMENT_FIELDS, "description")


def slim_assignment_detail(assignment: dict[str, Any]) -> dict[str, Any]:
    """One assignment, including its description as bounded plain text.

    The description is written by a teacher, so it goes through
    `sanitize.sanitize()`: markup out, size capped, and wrapped in delimiters
    that name where it came from. See `SCOPE.md` section 6 — that mitigates,
    it does not solve.
    """
    description = assignment.get("description")
    return {
        **slim_assignment(assignment),
        "description": (
            sanitize(description, "assignment description") if description else None
        ),
    }

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


# `SCOPE.md` section 3: title, date, plain-text body. The author is left out
# deliberately — it is a third party's name, pronouns and avatar url, and none
# of that is needed to answer "are there new announcements".
ANNOUNCEMENT_FIELDS = ("title", "posted_at", "message")


def slim_announcement(announcement: dict[str, Any]) -> dict[str, Any]:
    """Reduce one announcement to its title, date and text.

    The body is written by a teacher, so it goes through the sanitizer: markup
    out, size capped, wrapped in delimiters naming where it came from.
    """
    message = announcement.get("message")
    return {
        "title": announcement.get("title"),
        "posted_at": announcement.get("posted_at"),
        "message": sanitize(message, "announcement") if message else None,
    }


# A module item, reduced. `id` is the content id, not the item id: it is what
# read_file will need in v0.2, and modules are the only place it can come from
# because the course file index is 403 for students (`SCOPE.md` section 2).
MATERIAL_ITEM_FIELDS = ("title", "type", "id")
MODULE_FIELDS = ("module", "locked", "sections")

# A SubHeader is a label a teacher put between items. It is not content, so it
# becomes the name of the section that follows rather than an entry in it.
SUBHEADER = "SubHeader"


def slim_module_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "type": item.get("type"),
        "id": item.get("content_id"),
    }


def group_into_sections(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten a module's items into named sections.

    A SubHeader opens a section and everything after it belongs there, until
    the next SubHeader. Items appearing before any SubHeader go into a section
    with no name.

    Membership is sequential rather than taken from `indent`. Indent is how
    deeply Canvas draws an item, not what it belongs to — grouping by it would
    put an item in the wrong place the moment a teacher indents something for
    looks.
    """
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {"section": None, "items": []}

    for item in items:
        if item.get("type") == SUBHEADER:
            if current["items"] or current["section"] is not None:
                sections.append(current)
            current = {"section": item.get("title"), "items": []}
            continue
        if item.get("hidden_for_user"):
            continue
        current["items"].append(slim_module_item(item))

    if current["items"] or current["section"] is not None:
        sections.append(current)
    return sections


def slim_module(module: dict[str, Any]) -> dict[str, Any]:
    """One module, with its items grouped under their subheaders.

    A locked module keeps its name but loses its contents. `SCOPE.md` section 5
    reads locked as "you may not have this" for modules and files, unlike
    assignments — but hiding the module entirely would hide the shape of the
    course, which is not what is being protected.
    """
    locked = module.get("state") == "locked"
    return {
        "module": module.get("name"),
        "locked": locked,
        "sections": [] if locked else group_into_sections(module.get("items") or []),
    }

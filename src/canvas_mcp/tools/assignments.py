"""The `list_assignments` tool."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import slim_assignment

ASSIGNMENT_PARAMS: dict[str, Any] = {
    # Without the submission there is no way to say whether it was handed in.
    "include[]": ["submission"],
    "order_by": "due_at",
}


def is_hidden(assignment: dict[str, Any]) -> bool:
    """Whether Canvas says this assignment does not exist for this student.

    `hidden_for_user` means the student may not see it, so it is dropped —
    `SCOPE.md` section 5. `locked_for_user` is different: it means the
    assignment cannot be submitted to right now, which is something a student
    needs to be told rather than kept from.
    """
    return bool(assignment.get("hidden_for_user"))


def is_upcoming(assignment: dict[str, Any], now: datetime) -> bool:
    """Whether the deadline is still ahead.

    An assignment with no due date counts as upcoming. Dropping it would hide
    work that still has to be done, and there is no date on which to decide it
    has passed.
    """
    due_at = assignment.get("due_at")
    if not due_at:
        return True
    try:
        return datetime.fromisoformat(due_at) >= now
    except ValueError:
        return True


def make_list_assignments(client: CanvasClient) -> Callable[..., list[dict[str, Any]]]:
    """Build the tool, with the client closed over rather than passed in."""

    def list_assignments(
        course_id: int,
        only_upcoming: bool = False,
    ) -> list[dict[str, Any]]:
        """List the assignments for one course, with deadlines.

        Returns the assignment id, name, due date, points, whether it has been
        submitted, and whether it is currently locked. Requires a course id
        from list_courses.

        Everything is returned by default, including work that is already past
        its deadline — a student often wants exactly that. Pass
        only_upcoming=true for deadlines that have not passed yet; assignments
        with no due date are always included, because there is no date on which
        to decide they are over.

        A locked assignment is one that cannot be submitted to right now. It is
        still listed, because knowing it exists is the point.
        """
        raw = [
            assignment
            for assignment in client.paginate(
                f"/courses/{int(course_id)}/assignments", params=ASSIGNMENT_PARAMS
            )
            if not is_hidden(assignment)
        ]
        if only_upcoming:
            now = datetime.now(UTC)
            raw = [a for a in raw if is_upcoming(a, now)]
        return [slim_assignment(assignment) for assignment in raw]

    return list_assignments

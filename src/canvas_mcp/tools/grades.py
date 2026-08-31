"""The `list_grades` tool.

Off by default. The token this server holds may read these scores; the server
may not, unless someone starts it with `grades:read`. That gap is the
demonstration the project exists for — see `SCOPE.md` sections 2 and 3.
"""

from collections.abc import Callable
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import slim_submission

SUBMISSION_PARAMS: dict[str, Any] = {
    "student_ids[]": ["self"],
    # Without the assignment object a score is a number attached to an id.
    "include[]": ["assignment"],
}


def make_list_grades(client: CanvasClient) -> Callable[..., list[dict[str, Any]]]:
    """Build the tool, with the client closed over rather than passed in."""

    def list_grades(course_id: int) -> list[dict[str, Any]]:
        """Show the scores for one course, per assignment.

        Returns the assignment name, the score, the maximum, the letter grade
        if the course uses one, and flags for late, missing or excused work.
        Requires a course id from list_courses. Covers a single course on
        purpose: there is no way to ask about every course at once.

        Final course grades are not available — this institution hides them.
        """
        submissions = client.paginate(
            # Coerced rather than trusted: this argument is chosen by a model.
            f"/courses/{int(course_id)}/students/submissions",
            params=SUBMISSION_PARAMS,
        )
        return [slim_submission(submission) for submission in submissions]

    return list_grades

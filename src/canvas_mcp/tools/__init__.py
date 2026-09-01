"""Tool factories.

Each tool is built from a client rather than taking one as an argument. Tool
arguments are chosen by a model; a `client` parameter would put the connection
— and through it the token — inside something the model can influence.
"""

from collections.abc import Callable
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.tools.announcements import make_list_announcements
from canvas_mcp.tools.assignments import (
    make_get_assignment,
    make_list_assignments,
)
from canvas_mcp.tools.courses import make_list_courses
from canvas_mcp.tools.grades import make_list_grades
from canvas_mcp.tools.materials import make_list_materials

# What a client shows a person. The function name is for the model, this is
# for the human reading their client's tool list.
TOOL_TITLES = {
    "list_courses": "My courses",
    "list_assignments": "Deadlines",
    "get_assignment": "Assignment details",
    "list_announcements": "Announcements",
    "list_materials": "Course materials",
    "list_grades": "Scores per assignment",
}


def build_tools(client: CanvasClient) -> dict[str, Callable[..., Any]]:
    """Every tool this project implements, by name.

    The names must match `TOOL_SCOPES` in `scopes.py`; the registry refuses to
    start otherwise.
    """
    return {
        "list_courses": make_list_courses(client),
        "list_assignments": make_list_assignments(client),
        "get_assignment": make_get_assignment(client),
        "list_announcements": make_list_announcements(client),
        "list_materials": make_list_materials(client),
        "list_grades": make_list_grades(client),
    }

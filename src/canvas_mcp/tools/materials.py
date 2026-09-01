"""The `list_materials` tool.

Named `list_materials` rather than `list_files` on purpose: the source is the
module tree, and what comes back includes pages and assignments, not only
files. It is also the only way in — `GET /courses/:id/files` returns 403 for a
student token (`SCOPE.md` section 2).
"""

from collections.abc import Callable
from typing import Any

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import slim_module

MODULE_PARAMS: dict[str, Any] = {"include[]": ["items"]}


def make_list_materials(client: CanvasClient) -> Callable[..., list[dict[str, Any]]]:
    """Build the tool, with the client closed over rather than passed in."""

    def list_materials(
        course_id: int,
        module_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show what a course publishes, module by module.

        Returns each module with its items grouped under the subheaders the
        teacher wrote, and for every item its title, its type (File, Page,
        Assignment, Quiz) and the id a file needs to be read later.

        Optionally filter by module name, for example "Week 1" — matching is
        case-insensitive and partial.

        This is the only route to a course's files: the file index itself is
        closed to students. A locked module is listed by name without its
        contents, so the shape of the course stays visible.
        """
        modules = [
            slim_module(module)
            for module in client.paginate(
                f"/courses/{int(course_id)}/modules", params=MODULE_PARAMS
            )
        ]
        if module_filter is None:
            return modules
        wanted = module_filter.casefold()
        return [m for m in modules if m["module"] and wanted in m["module"].casefold()]

    return list_materials

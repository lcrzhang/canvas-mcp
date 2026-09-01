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
        """What a course publishes: slides, readers, pages, per week.

        Use this for "which slides belong to week 3" or "where is the reader".
        It is the only route to a course's files — Canvas closes the file list
        itself to students, so a file id can only come from here.

        Returns each module with its items grouped under the headings the
        teacher wrote. Every item has a title and a type: File, Page,
        Assignment or Quiz.

        Only a File carries an id, and only a File can be read with read_file.
        A Page has no file behind it — its title is all there is here, and its
        contents are not available through this server. Assignments appear in
        this list too, but list_assignments is the better tool for deadlines
        and get_assignment for what one asks.

        module_filter matches part of a module name, case-insensitively:
        "week 3" or "practical". An empty result means no module matched, not
        that the course publishes nothing — course structure varies, and a
        module for a given week may simply not exist yet. Call again without
        the filter to see what is there.

        A locked module is listed by name with no contents, so the shape of the
        course stays visible even where the material is not.
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

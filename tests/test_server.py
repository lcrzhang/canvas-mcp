"""What the server exposes, and what it must not.

The load-bearing test is `test_a_disabled_tool_is_absent_from_the_tool_list`:
it is the project's claim, asserted rather than argued.
"""

import asyncio
import json
from pathlib import Path

import httpx2
import pytest

from canvas_mcp.client import CanvasClient
from canvas_mcp.filters import SUBMISSION_FIELDS
from canvas_mcp.scopes import DEFAULT_SCOPES, TOOL_SCOPES
from canvas_mcp.server import build_server, parse_args
from canvas_mcp.tools import build_tools
from canvas_mcp.tools.courses import make_list_courses
from canvas_mcp.tools.grades import make_list_grades

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE = FIXTURES / "courses.json"
SUBMISSIONS_FIXTURE = FIXTURES / "submissions.json"


def stub() -> object:
    def tool(course_id: int | None = None) -> list[dict]:
        """A stand-in tool."""
        return []

    return tool


def tool_names(server: object) -> list[str]:
    return sorted(tool.name for tool in asyncio.run(server.list_tools()))


def test_a_disabled_tool_is_absent_from_the_tool_list() -> None:
    """The claim: the token may read grades, this server may not."""
    server = build_server({"list_courses": stub(), "list_grades": stub()})
    assert tool_names(server) == ["list_courses"]


def test_the_disabled_tool_appears_once_its_scope_is_asked_for() -> None:
    server = build_server(
        {"list_courses": stub(), "list_grades": stub()},
        scopes=[*DEFAULT_SCOPES, "grades:read"],
    )
    assert tool_names(server) == ["list_courses", "list_grades"]


def test_one_scope_registers_one_tool() -> None:
    server = build_server({"list_courses": stub()}, scopes=["courses:read"])
    assert tool_names(server) == ["list_courses"]


def test_every_registered_tool_is_marked_read_only() -> None:
    server = build_server({"list_courses": stub()})
    for tool in asyncio.run(server.list_tools()):
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


def test_the_startup_line_never_touches_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """stdout carries the MCP protocol; a stray print corrupts the stream."""
    build_server({"list_courses": stub()})
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "courses:read" in captured.err
    assert "grades:read" in captured.err  # reported as disabled


def test_scopes_are_split_on_commas() -> None:
    assert parse_args(["--scopes", "courses:read,grades:read"]).scopes == (
        "courses:read,grades:read"
    )
    assert parse_args([]).scopes is None


# --- the tool itself ------------------------------------------------------


def fixture_client() -> CanvasClient:
    """A client serving the committed fixture, with no network."""
    payload = json.loads(FIXTURE.read_text())

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=payload)

    return CanvasClient(transport=httpx2.MockTransport(handler))


@pytest.fixture(autouse=True)
def _token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CANVAS_TOKEN", "fake-token-for-tests")


def test_list_courses_returns_slimmed_courses() -> None:
    with fixture_client() as client:
        courses = make_list_courses(client)()

    assert len(courses) == 6
    assert all(
        set(course) == {"id", "name", "course_code", "term"} for course in courses
    )
    assert "calendar" not in json.dumps(courses)


def test_term_filter_matches_case_insensitively_and_partially() -> None:
    with fixture_client() as client:
        list_courses = make_list_courses(client)
        term = list_courses()[0]["term"]
        assert list_courses(term_filter=term[:6].lower())
        assert list_courses(term_filter="no such term") == []


# --- policy and tools stay in step ----------------------------------------

# Tools named in TOOL_SCOPES that have not been written yet. Step 4 moved this
# check out of the registry so the server could start while the tools were
# still arriving; here is where it went. Adding a tool fails this test until
# its name is removed from the list, which is the point.
NOT_YET_BUILT = {
    "list_assignments",
    "get_assignment",
    "list_announcements",
    "list_materials",
}


def test_every_policy_row_names_a_tool_that_exists_or_is_listed_as_pending() -> None:
    with fixture_client() as client:
        built = set(build_tools(client))
    assert set(TOOL_SCOPES) - built == NOT_YET_BUILT
    assert built <= set(TOOL_SCOPES)


def test_the_real_tools_register_under_the_default_scopes() -> None:
    with fixture_client() as client:
        server = build_server(build_tools(client))
    assert tool_names(server) == ["list_courses"]


def test_list_grades_appears_only_when_its_scope_is_asked_for() -> None:
    with fixture_client() as client:
        server = build_server(
            build_tools(client), scopes=[*DEFAULT_SCOPES, "grades:read"]
        )
    assert tool_names(server) == ["list_courses", "list_grades"]


def test_list_grades_returns_slimmed_submissions() -> None:
    payload = json.loads(SUBMISSIONS_FIXTURE.read_text())

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=payload)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        scores = make_list_grades(client)(course_id=1)

    assert len(scores) == len(payload)
    assert all(tuple(score) == SUBMISSION_FIELDS for score in scores)
    assert "secure_params" not in json.dumps(scores)

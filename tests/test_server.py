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
from canvas_mcp.scopes import DEFAULT_SCOPES
from canvas_mcp.server import build_server, parse_args
from canvas_mcp.tools.courses import make_list_courses

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "courses.json"


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

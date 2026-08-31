"""What the server exposes, and what it must not.

The load-bearing test is `test_a_disabled_tool_is_absent_from_the_tool_list`:
it is the project's claim, asserted rather than argued.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.filters import ASSIGNMENT_FIELDS, SUBMISSION_FIELDS
from canvas_mcp.scopes import DEFAULT_SCOPES, TOOL_SCOPES
from canvas_mcp.server import build_client, build_server, parse_args
from canvas_mcp.tools import build_tools
from canvas_mcp.tools.assignments import is_upcoming, make_list_assignments
from canvas_mcp.tools.courses import make_list_courses, term_has_ended
from canvas_mcp.tools.grades import make_list_grades

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE = FIXTURES / "courses.json"
SUBMISSIONS_FIXTURE = FIXTURES / "submissions.json"
ASSIGNMENTS_FIXTURE = FIXTURES / "assignments.json"


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
    """Asserted by claim rather than by inventory: the exact list grows every
    step, and keeping it in step is what the policy tripwire above is for."""
    with fixture_client() as client:
        server = build_server(build_tools(client))
    names = tool_names(server)
    assert "list_courses" in names
    assert "list_assignments" in names
    assert "list_grades" not in names


def test_list_grades_appears_only_when_its_scope_is_asked_for() -> None:
    with fixture_client() as client:
        server = build_server(
            build_tools(client), scopes=[*DEFAULT_SCOPES, "grades:read"]
        )
    assert "list_grades" in tool_names(server)


def test_list_grades_returns_slimmed_submissions() -> None:
    payload = json.loads(SUBMISSIONS_FIXTURE.read_text())

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=payload)

    with CanvasClient(transport=httpx2.MockTransport(handler)) as client:
        scores = make_list_grades(client)(course_id=1)

    assert len(scores) == len(payload)
    assert all(tuple(score) == SUBMISSION_FIELDS for score in scores)
    assert "secure_params" not in json.dumps(scores)


def test_demo_mode_needs_no_token_and_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CANVAS_TOKEN", raising=False)
    client = build_client(demo=True)
    assert client.verify_token()["name"] == "Demo Student"
    assert client.base_url == "https://canvas.example.edu"


def test_demo_mode_404s_an_endpoint_it_has_no_fixture_for() -> None:
    client = build_client(demo=True)
    with pytest.raises(CanvasError, match="not found"):
        client.get("/courses/1/modules")


# --- current courses ------------------------------------------------------

NOW = datetime(2026, 8, 31, tzinfo=UTC)


@pytest.mark.parametrize(
    ("end_at", "ended"),
    [
        ("2025-07-01T00:00:00Z", True),
        ("2027-07-01T00:00:00Z", False),
        (None, False),  # an open-ended term is a real thing
        ("not a date", False),  # never hide a course over a parse failure
    ],
)
def test_term_has_ended(end_at: str | None, ended: bool) -> None:
    assert term_has_ended({"term": {"end_at": end_at}}, NOW) is ended


def test_a_course_without_a_term_is_never_hidden() -> None:
    assert term_has_ended({}, NOW) is False


def courses_client(courses: list[dict]) -> CanvasClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=courses)

    return CanvasClient(transport=httpx2.MockTransport(handler))


FINISHED = {
    "id": 1,
    "name": "Matching KI",
    "course_code": "OLD",
    "term": {"name": "2024/25 semester 2", "end_at": "2025-07-01T00:00:00Z"},
}
RUNNING = {
    "id": 2,
    "name": "Datastructuren",
    "course_code": "NEW",
    "term": {"name": "2026/27 semester 1", "end_at": "2027-02-01T00:00:00Z"},
}


def test_finished_terms_are_left_out_by_default() -> None:
    """Canvas keeps an enrolment active long after the term ends, so the
    unfiltered answer mixes this year's courses with ones from years ago."""
    with courses_client([FINISHED, RUNNING]) as client:
        names = [course["name"] for course in make_list_courses(client)()]
    assert names == ["Datastructuren"]


def test_current_only_false_shows_everything() -> None:
    with courses_client([FINISHED, RUNNING]) as client:
        courses = make_list_courses(client)(current_only=False)
    assert len(courses) == 2


def test_term_filter_still_applies_within_current_courses() -> None:
    with courses_client([FINISHED, RUNNING]) as client:
        list_courses = make_list_courses(client)
        assert list_courses(term_filter="2026/27")
        assert list_courses(term_filter="2024/25") == []
        assert list_courses(term_filter="2024/25", current_only=False)


# --- assignments ----------------------------------------------------------

VISIBLE = {"id": 1, "name": "Visible", "due_at": "2027-01-01T00:00:00Z"}
HIDDEN = {"id": 2, "name": "Hidden", "hidden_for_user": True}
PAST = {"id": 3, "name": "Past", "due_at": "2025-01-01T00:00:00Z"}
UNDATED = {"id": 4, "name": "Undated", "due_at": None}


@pytest.mark.parametrize(
    ("due_at", "upcoming"),
    [
        ("2027-01-01T00:00:00Z", True),
        ("2025-01-01T00:00:00Z", False),
        (None, True),  # nothing to decide it has passed
        ("not a date", True),
    ],
)
def test_is_upcoming(due_at: str | None, upcoming: bool) -> None:
    assert is_upcoming({"due_at": due_at}, NOW) is upcoming


def test_hidden_assignments_are_dropped_but_locked_ones_are_not() -> None:
    """SCOPE.md section 5 says hidden means the item does not exist for the
    tool. Locked means it cannot be submitted to, which a student needs told."""
    locked = {**VISIBLE, "locked_for_user": True}
    with courses_client([locked, HIDDEN]) as client:
        listed = make_list_assignments(client)(course_id=1)
    assert [a["name"] for a in listed] == ["Visible"]
    assert listed[0]["locked"] is True


def test_everything_is_returned_by_default_including_past_deadlines() -> None:
    with courses_client([VISIBLE, PAST, UNDATED]) as client:
        listed = make_list_assignments(client)(course_id=1)
    assert len(listed) == 3


def test_only_upcoming_keeps_undated_work() -> None:
    with courses_client([VISIBLE, PAST, UNDATED]) as client:
        listed = make_list_assignments(client)(course_id=1, only_upcoming=True)
    assert sorted(a["name"] for a in listed) == ["Undated", "Visible"]


def test_list_assignments_runs_against_the_committed_fixture() -> None:
    payload = json.loads(ASSIGNMENTS_FIXTURE.read_text())
    with courses_client(payload) as client:
        listed = make_list_assignments(client)(course_id=1)
    assert len(listed) == len(payload)
    assert all(tuple(a) == ASSIGNMENT_FIELDS for a in listed)
    assert "secure_params" not in json.dumps(listed)

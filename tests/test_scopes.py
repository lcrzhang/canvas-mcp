"""The contract for `canvas_mcp.scopes`, written before the implementation.

These tests are the specification for roadmap step 4. The module they import
does not exist yet; making them pass is the step. They pin behaviour, not
implementation — how the registry stores things is not asserted anywhere.

What `src/canvas_mcp/scopes.py` must provide:

    TOOL_SCOPES: dict[str, str]
        The policy, on one page: tool name -> the scope that enables it.

    DEFAULT_SCOPES: tuple[str, ...]
        An explicit list, not a rule. "Everything except grades:read" would
        grow on its own when a tool is added; a written list only changes when
        somebody changes it.

    ScopeError(Exception)
        Raised for a configuration mistake. Not a Canvas API error.

    ScopeRegistry(tools, scopes=None)
        `tools` maps a tool name to whatever represents that tool — the real
        functions in step 5, plain objects in these tests. The registry only
        looks at the keys, so it needs to know nothing about MCP.
        `scopes=None` means DEFAULT_SCOPES. Every failure is raised here, at
        construction, so a misconfigured server does not start.

    .enabled_tools() -> dict[str, T]
        The subset the caller may register. Nothing outside this may be
        exposed, which is why the registry hands out the tools rather than
        answering questions about scopes: `server.py` cannot register what it
        was never given.

    .scopes -> frozenset[str]
        The resolved scope set, so the server can print one line at startup
        saying what is on and what is off.
"""

import pytest

from canvas_mcp.scopes import (
    DEFAULT_SCOPES,
    TOOL_SCOPES,
    ScopeError,
    ScopeRegistry,
)


def all_tools() -> dict[str, object]:
    """A stand-in for every tool the project will have."""
    return {name: object() for name in TOOL_SCOPES}


# --- what is exposed ------------------------------------------------------


def test_the_default_is_an_explicit_list_of_four_read_scopes() -> None:
    assert set(DEFAULT_SCOPES) == {
        "courses:read",
        "assignments:read",
        "announcements:read",
        "materials:read",
    }


def test_grades_is_not_in_the_default() -> None:
    assert "grades:read" not in DEFAULT_SCOPES
    assert "grades:read" in TOOL_SCOPES.values()  # it exists; it is just off


def test_without_scopes_the_default_set_is_used() -> None:
    registry = ScopeRegistry(all_tools())
    assert registry.scopes == frozenset(DEFAULT_SCOPES)


def test_one_scope_exposes_exactly_one_tool() -> None:
    registry = ScopeRegistry(all_tools(), scopes=["courses:read"])
    assert list(registry.enabled_tools()) == ["list_courses"]


def test_a_disabled_tool_is_absent_rather_than_present_and_refusing() -> None:
    registry = ScopeRegistry(all_tools())
    # The whole point: the model cannot see it, so it cannot try.
    assert "list_grades" not in registry.enabled_tools()


def test_grades_is_reachable_once_it_is_asked_for() -> None:
    """The demonstration: the token always allowed this, the server did not."""
    registry = ScopeRegistry(all_tools(), scopes=[*DEFAULT_SCOPES, "grades:read"])
    assert "list_grades" in registry.enabled_tools()


def test_an_explicitly_empty_scope_list_exposes_nothing() -> None:
    """Distinct from omitting the argument, which means 'use the default'."""
    registry = ScopeRegistry(all_tools(), scopes=[])
    assert registry.enabled_tools() == {}


def test_enabled_tools_hands_back_the_objects_it_was_given() -> None:
    tools = all_tools()
    enabled = ScopeRegistry(tools, scopes=["courses:read"]).enabled_tools()
    assert enabled["list_courses"] is tools["list_courses"]


# --- what refuses to start ------------------------------------------------


def test_an_unknown_scope_fails_at_construction() -> None:
    with pytest.raises(ScopeError) as excinfo:
        ScopeRegistry(all_tools(), scopes=["courses:raed"])

    message = str(excinfo.value)
    assert "courses:raed" in message
    # A typo must not produce a silently empty server, so the message has to
    # say what the valid scopes are.
    assert "courses:read" in message


def test_a_wildcard_is_not_a_scope() -> None:
    with pytest.raises(ScopeError):
        ScopeRegistry(all_tools(), scopes=["courses:*"])


def test_a_tool_missing_from_the_policy_table_fails_at_construction() -> None:
    tools = all_tools() | {"list_syllabus": object()}
    with pytest.raises(ScopeError, match="list_syllabus"):
        ScopeRegistry(tools)


def test_a_policy_row_without_a_tool_is_allowed_while_tools_are_built() -> None:
    """The mirror of the check above, and deliberately not enforced.

    A policy row naming a tool that does not exist yet is stale documentation,
    not a leak. Enforcing it at construction would stop the server from
    starting until every tool in the table had been written, which is the
    opposite of building one step at a time. Step 5 adds the test that catches
    a genuinely stale row, once every tool is known.
    """
    tools = all_tools()
    del tools[next(iter(TOOL_SCOPES))]
    registry = ScopeRegistry(tools)
    assert next(iter(TOOL_SCOPES)) not in registry.enabled_tools()


def test_every_scope_in_the_table_is_spelled_consistently() -> None:
    for tool, scope in TOOL_SCOPES.items():
        assert ":" in scope, f"{tool} has a malformed scope: {scope}"
        assert scope == scope.lower()
        assert "*" not in scope

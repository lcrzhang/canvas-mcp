"""What every tool promises a model before it is called.

Roadmap step 13 is about descriptions, and no test can judge whether one reads
well. These pin the things that are checkable — a description exists, a title
exists, every argument has a type, required arguments are the ones without a
default — so a regression in any of them fails rather than being noticed later
in a wrong answer.
"""

import asyncio
from typing import Any

import pytest

from canvas_mcp.client import CanvasClient
from canvas_mcp.scopes import DEFAULT_SCOPES, TOOL_SCOPES
from canvas_mcp.server import build_client, build_server
from canvas_mcp.tools import TOOL_TITLES, build_tools

ALL_SCOPES = sorted(set(TOOL_SCOPES.values()))


def every_tool() -> list[Any]:
    client: CanvasClient = build_client(demo=True)
    server = build_server(build_tools(client), scopes=ALL_SCOPES)
    return asyncio.run(server.list_tools())


TOOLS = every_tool()


def has_a_type(schema: dict[str, Any]) -> bool:
    """A usable schema names a type, directly or through a union."""
    if "type" in schema:
        return True
    return all("type" in option for option in schema.get("anyOf", []))


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_tool_says_what_it_is_for(tool: Any) -> None:
    assert tool.description and len(tool.description.split()) > 20
    assert tool.title, f"{tool.name} has no human-readable title"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_every_argument_has_a_type(tool: Any) -> None:
    """An argument with no type tells a model nothing about what to pass."""
    for name, schema in tool.input_schema.get("properties", {}).items():
        assert has_a_type(schema), f"{tool.name}.{name} has no type: {schema}"


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t.name)
def test_required_arguments_are_the_ones_without_a_default(tool: Any) -> None:
    properties = tool.input_schema.get("properties", {})
    required = set(tool.input_schema.get("required", []))
    assert required == {n for n, s in properties.items() if "default" not in s}


def test_every_course_scoped_tool_takes_a_course_id() -> None:
    """The id can only come from list_courses, so every other tool needs it."""
    for tool in TOOLS:
        if tool.name == "list_courses":
            continue
        assert "course_id" in tool.input_schema.get("properties", {})


def test_every_tool_is_titled_and_no_title_is_orphaned() -> None:
    assert set(TOOL_TITLES) == set(TOOL_SCOPES)


def test_the_default_tool_list_is_the_one_a_student_gets() -> None:
    client = build_client(demo=True)
    server = build_server(build_tools(client), scopes=list(DEFAULT_SCOPES))
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert "list_grades" not in names
    assert len(names) == len(TOOL_SCOPES) - 1


# --- what the server says about itself ------------------------------------


def test_the_instructions_explain_an_absence_without_naming_it() -> None:
    """Observed on 2026-09-01: asked for grades with `grades:read` off, a model
    reported the tool as "not built yet". The tool exists and is switched off,
    and the model cannot tell — that is the point of not registering it. So the
    server says absence is configuration, without saying what is absent."""
    server = build_server(build_tools(build_client(demo=True)))
    instructions = server.instructions or ""

    assert "configuration" in instructions
    assert "estimate" in instructions
    # It must not leak what was withheld — that would undo the choice.
    assert "grades" not in instructions.lower()
    assert "list_" not in instructions


def test_the_instructions_are_the_same_whatever_is_enabled() -> None:
    """A different string per configuration would let a model infer the shape
    of what it cannot see."""
    demo = build_tools(build_client(demo=True))
    narrow = build_server(demo, scopes=["courses:read"]).instructions
    wide = build_server(demo, scopes=ALL_SCOPES).instructions
    assert narrow == wide

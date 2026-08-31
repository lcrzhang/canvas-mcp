"""The server started as a real process, speaking the real protocol.

Every other test exercises a module. This one runs `canvas_mcp.server` in a
subprocess and talks to it over stdio exactly as a client does: initialize,
list the tools, call one. It is the difference between "the parts work" and
"the server serves".

It needs no token and no network — `--demo` answers from `fixtures/`, which is
the reason step 11 was pulled forward.
"""

import asyncio
import json
import os
import sys
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Deliberately without CANVAS_TOKEN: demo mode must not need one.
CHILD_ENV = {
    key: value
    for key, value in os.environ.items()
    if key not in {"CANVAS_TOKEN", "CANVAS_BASE_URL"}
}


async def _session(scopes: str) -> tuple[list[str], Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "canvas_mcp.server", "--demo", "--scopes", scopes],
        env=CHILD_ENV,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(tool.name for tool in listed.tools)
            called = await session.call_tool("list_courses", {})
            return names, called


def run(scopes: str) -> tuple[list[str], Any]:
    return asyncio.run(_session(scopes))


def test_the_server_starts_and_answers_over_stdio() -> None:
    names, result = run("courses:read")

    assert names == ["list_courses"]
    assert not result.is_error

    # The SDK returns one content block per list item, and the same payload
    # again under structured_content. Both are checked: a client may read
    # either.
    assert len(result.content) == 6
    first = json.loads(result.content[0].text)
    assert set(first) == {"id", "name", "course_code", "term"}
    assert result.structured_content is not None
    assert len(result.structured_content["result"]) == 6


def test_nothing_but_the_protocol_is_written_to_stdout() -> None:
    """A stray print on stdout corrupts the stream; the session completing at
    all is the proof, since a malformed frame would fail the handshake."""
    names, result = run("courses:read")
    assert names and not result.is_error


def test_the_scope_gap_holds_across_a_real_protocol_session() -> None:
    """The project's claim, end to end: the flag decides what exists."""
    without, _ = run("courses:read")
    with_grades, _ = run("courses:read,grades:read")

    assert "list_grades" not in without
    assert "list_grades" in with_grades

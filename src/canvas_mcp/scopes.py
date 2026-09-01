"""Deny-by-default tool registration.

A Canvas personal access token is unscoped: it carries every permission of the
person who created it. This module is the only place where less than that is
enforced, which is the point of the project rather than a detail of it.

The design decisions, their alternatives and the reasons are recorded in
`ROADMAP.md` step 4. Three of them shape this file:

- A tool outside the enabled scopes is **not registered**, rather than
  registered and refusing. A forgotten registration is an annoyance; a
  forgotten permission check is a leak.
- The registry **hands out tools** instead of answering questions about
  scopes, so a caller cannot register something it was never given.
- Everything that could leak fails **at construction**, so a misconfigured
  server does not start rather than misbehaving later. What cannot leak — a
  policy row for a tool that does not exist yet — is checked by the tests
  instead, so that building the tools one step at a time stays possible.
"""

from collections.abc import Iterable, Mapping
from typing import TypeVar

T = TypeVar("T")

# The policy, on one page. Adding a tool without adding it here stops the
# server from starting — see ScopeRegistry.__init__.
TOOL_SCOPES: dict[str, str] = {
    "list_courses": "courses:read",
    "list_assignments": "assignments:read",
    "get_assignment": "assignments:read",
    "list_announcements": "announcements:read",
    "list_materials": "materials:read",
    "list_grades": "grades:read",
    "read_file": "files:content",
}

# An explicit list, not a rule. "Everything except grades:read" would grow by
# itself the moment a tool is added, and the README documenting the default
# would quietly become false.
DEFAULT_SCOPES: tuple[str, ...] = (
    "courses:read",
    "assignments:read",
    "announcements:read",
    "materials:read",
    # Reading a slide is what a study assistant is for, and the file is one the
    # student can already open in Canvas. Unlike grades:read this is not the
    # capability being withheld.
    "files:content",
)


def known_scopes() -> tuple[str, ...]:
    """Every scope that exists, derived from the policy so it cannot drift."""
    return tuple(sorted(set(TOOL_SCOPES.values())))


class ScopeError(Exception):
    """A configuration mistake, raised before the server starts.

    Not a Canvas API error: nothing here has talked to Canvas yet.
    """


class ScopeRegistry:
    """Decides which tools may be registered, and hands them out.

    `tools` maps a tool name to whatever represents that tool — the real
    functions in the server, plain objects in the tests. Only the keys are
    read, so this module knows nothing about MCP, HTTP or Canvas.

    `scopes=None` means `DEFAULT_SCOPES`. An empty iterable is a different
    thing: it means the operator asked for nothing, and gets nothing.
    """

    def __init__(
        self,
        tools: Mapping[str, T],
        scopes: Iterable[str] | None = None,
    ) -> None:
        self._check_every_tool_is_policed(tools)
        requested = tuple(DEFAULT_SCOPES if scopes is None else scopes)
        self._check_scopes_exist(requested)

        self._tools: dict[str, T] = dict(tools)
        self.scopes: frozenset[str] = frozenset(requested)

    @staticmethod
    def _check_every_tool_is_policed(tools: Mapping[str, T]) -> None:
        """Refuse a tool that has no entry in the policy table.

        Only this direction is enforced at runtime. The mirror case — a policy
        row naming a tool that was not supplied — is stale documentation, not
        a leak, and enforcing it here would stop the server from starting
        while the tools are still being built one step at a time. That check
        lives in the test suite instead, where every tool is known.
        """
        unpoliced = sorted(set(tools) - set(TOOL_SCOPES))
        if unpoliced:
            raise ScopeError(
                f"No entry in TOOL_SCOPES for: {', '.join(unpoliced)}. "
                "A tool without a scope would run unpoliced, so add it to the "
                "policy table in scopes.py."
            )

    @staticmethod
    def _check_scopes_exist(requested: Iterable[str]) -> None:
        unknown = sorted(set(requested) - set(known_scopes()))
        if unknown:
            raise ScopeError(
                f"Unknown scope: {', '.join(unknown)}. "
                f"Valid scopes are: {', '.join(known_scopes())}. "
                "Wildcards are not supported — name each scope."
            )

    def enabled_tools(self) -> dict[str, T]:
        """The tools the caller may register, and nothing else."""
        return {
            name: tool
            for name, tool in self._tools.items()
            if TOOL_SCOPES[name] in self.scopes
        }

    def disabled_scopes(self) -> tuple[str, ...]:
        """For the startup line: what exists but was not asked for."""
        return tuple(scope for scope in known_scopes() if scope not in self.scopes)

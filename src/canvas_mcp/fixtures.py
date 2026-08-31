"""Checks that a fixture contains nothing real.

Fixtures ship inside a public repository, which makes them the one place live
API data could enter the repo — permanently, because removing a blob in a later
commit does not remove it from history. This module is the check that runs
before a fixture is written, and again in CI over everything already there.

Findings name the JSON path and the reason, never the offending value: a guard
that echoes a token into a CI log has leaked it just the same.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# A fixture may mention these hosts and no others.
ALLOWED_HOST_SUFFIXES = ("example.edu", "example.com", "example.org")
ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Values the conversion is expected to produce carry this prefix.
SYNTHETIC_PREFIX = "FIXTURE"

_URL_HOST = re.compile(r"https?://([^/\s\"']+)")
_EMAIL_DOMAIN = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")
_VERIFIER = re.compile(r"verifier=([^&\s\"']*)")
# Canvas personal access tokens look like 12345~<40+ random characters>.
_CANVAS_TOKEN = re.compile(r"\b\d{3,}~[A-Za-z0-9]{20,}\b")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _host_is_allowed(host: str) -> bool:
    host = host.split("@")[-1].split(":")[0].lower()
    if host in ALLOWED_HOSTS:
        return True
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in ALLOWED_HOST_SUFFIXES
    )


def _check_text(text: str, where: str) -> list[str]:
    findings: list[str] = []

    for host in _URL_HOST.findall(text):
        if not _host_is_allowed(host):
            findings.append(f"{where}: URL points at a real host ({host})")

    for domain in _EMAIL_DOMAIN.findall(text):
        if not _host_is_allowed(domain):
            findings.append(f"{where}: e-mail address on a real domain ({domain})")

    for verifier in _VERIFIER.findall(text):
        if not verifier.startswith(SYNTHETIC_PREFIX):
            findings.append(
                f"{where}: verifier= without the {SYNTHETIC_PREFIX} prefix — "
                "this is a working unauthenticated download link"
            )

    if _CANVAS_TOKEN.search(text):
        findings.append(f"{where}: looks like a Canvas access token")

    if _UUID.search(text):
        findings.append(f"{where}: canonical UUID, which the conversion replaces")

    if _LONG_HEX.search(text) and not text.startswith(SYNTHETIC_PREFIX):
        findings.append(f"{where}: 32+ character hex string, likely a real id")

    return findings


def find_real_looking_values(data: Any, where: str = "$") -> list[str]:
    """Walk a decoded JSON document and report anything that looks real.

    An empty list means the document is safe to commit.
    """
    if isinstance(data, str):
        return _check_text(data, where)
    if isinstance(data, dict):
        findings: list[str] = []
        for key, value in data.items():
            findings += find_real_looking_values(value, f"{where}.{key}")
        return findings
    if isinstance(data, list):
        findings = []
        for index, value in enumerate(data):
            findings += find_real_looking_values(value, f"{where}[{index}]")
        return findings
    return []


# --- conversion -----------------------------------------------------------
#
# The guard above is the second line of defence. This is the first, and it
# works the other way round: instead of removing fields known to be dangerous,
# it replaces *every* scalar value. Nothing real survives because nothing real
# is copied — which does not depend on having thought of every field.

SYNTHETIC_HOST = "canvas.example.edu"

# The one place an original value survives. These are enums the tools branch
# on, so replacing them would make a fixture useless. A value is only kept if
# it also *looks* like an enum — see _preserved().
PRESERVED_KEYS = frozenset(
    {
        "workflow_state",
        "state",
        "enrollment_state",
        "type",
        "content_type",
        "grading_type",
        "submission_types",
        "role",
    }
)
# No spaces: every Canvas enum is a single token ("available",
# "online_upload", "application/pdf"), while free text that happens to sit
# under an allowlisted key almost always has them. Spaces were allowed in
# the first version, which let "Uploaded by <name> on <date>" through as an
# enum. Slash and dot are allowed so MIME types survive.
_ENUM_SHAPE = re.compile(r"^[A-Za-z0-9_\-./+]{1,60}$")

_COURSE_NAMES = (
    "Introduction to Imaginary Systems",
    "Applied Handwaving",
    "Theory of Plausible Machines",
    "Advanced Placeholder Studies",
    "Seminar in Invented Methods",
    "Foundations of Nothing in Particular",
    "Comparative Hypotheticals",
    "Methods of Approximate Reasoning",
)
_TERM_NAMES = (
    "Semester 1 2026-2027",
    "Semester 2 2026-2027",
    "Summer 2027",
)
_ASSIGNMENT_NAMES = (
    "Weekly exercise 1",
    "Lab report",
    "Midterm essay",
    "Group project",
    "Reading response",
    "Problem set 4",
    "Final assignment",
)
# Points a real assignment is worth, rather than a counter climbing past 100.
_POINTS = (10.0, 20.0, 25.0, 50.0, 100.0)
# Kept below the smallest entry in _POINTS, so a synthetic score never exceeds
# the maximum it sits next to. Independent counters cannot guarantee a
# relationship; keeping the ranges apart can.
_SCORES = (6.5, 7.0, 8.0, 8.5, 9.5)
_LETTER_GRADES = ("A", "A-", "B+", "B", "C+")
_PERSON_NAMES = (
    "Robin Fictief",
    "Sam Verzonnen",
    "Kim Bedacht",
    "Alex Voorbeeld",
)
_PERSON_KEYS = frozenset(
    {"user_name", "display_name", "short_name", "sortable_name", "author_name"}
)
_COURSE_KEYS = frozenset({"name", "original_name", "friendly_name"})

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]|$)")
_BASE_DATE = date(2026, 2, 2)
# Fields that mean "this closes later". They are dated a year past the base so
# a captured fixture still reads as a running term rather than an archived one
# — a demo whose courses have all ended shows nothing, which is worse than a
# demo whose dates are approximate.
_FUTURE_DATE_KEYS = frozenset({"end_at", "lock_at", "unlock_at", "cached_due_date"})


def _preserved(key: str, value: str) -> bool:
    """Whether an original string may be kept verbatim.

    Being on the allowlist is not enough: the value must also look like an
    enum. A field that unexpectedly carries free text is replaced anyway,
    otherwise the allowlist is a hole rather than an exception.
    """
    return key in PRESERVED_KEYS and bool(_ENUM_SHAPE.match(value))


def _synthetic_string(key: str, value: str, n: int, parent: str = "") -> str:
    if _preserved(key, value):
        return value
    if key == "name":
        # The same key means different things depending on what it hangs off.
        # Without the parent, a term and a user were both given course names,
        # which read as a broken tool rather than as sample data.
        if parent == "term":
            return _TERM_NAMES[n % len(_TERM_NAMES)]
        if parent == "assignment":
            return _ASSIGNMENT_NAMES[n % len(_ASSIGNMENT_NAMES)]
        if parent == "user":
            return _PERSON_NAMES[n % len(_PERSON_NAMES)]
    if key in ("grade", "entered_grade"):
        # A letter grade rather than a number. FIXTURE-grade-1 reads as a bug,
        # and a number next to `score` invites a reader to check whether the
        # two agree — which independent counters cannot promise.
        return _LETTER_GRADES[n % len(_LETTER_GRADES)]
    if key == "ics" or value.endswith(".ics"):
        return f"https://{SYNTHETIC_HOST}/feeds/calendars/FIXTURE{n:02d}.ics"
    if "verifier=" in value:
        return (
            f"https://{SYNTHETIC_HOST}/files/{n}/download"
            f"?download_frd=1&verifier=FIXTURE{n:02d}"
        )
    if value.startswith(("http://", "https://")):
        return f"https://{SYNTHETIC_HOST}/api/v1/{key}/{n}"
    if _ISO_DATE.match(value):
        base = _BASE_DATE
        if key in _FUTURE_DATE_KEYS:
            base += timedelta(days=365)
        stamp = base + timedelta(days=n)
        return f"{stamp.isoformat()}T09:00:00Z" if "T" in value else stamp.isoformat()
    if "email" in key or key == "login_id":
        return f"person{n}@example.edu"
    if key in _PERSON_KEYS:
        return _PERSON_NAMES[n % len(_PERSON_NAMES)]
    if key == "course_code":
        # A code, not a title: course_code sharing the course name would make
        # the demo read as obviously fake data rather than as a course.
        return f"FIX{n:04d}SYN"
    if key in _COURSE_KEYS:
        return _COURSE_NAMES[n % len(_COURSE_NAMES)]
    if key == "uuid" or _UUID.match(value):
        return f"FIXTUREuuid{n:022d}"
    if "<" in value and ">" in value:
        return f"<p>Synthetic body {n} for {key}.</p>"
    return f"FIXTURE-{key}-{n}"


def to_synthetic(
    data: Any,
    key: str = "root",
    counters: dict | None = None,
    parent: str = "",
) -> Any:
    """Rebuild a decoded JSON document with every value replaced.

    Structure is preserved exactly — same keys, same nesting, same list
    lengths, same types — so a filter tested against the result still meets
    every field the live API sends, including ones nobody anticipated.

    Deterministic: the same input always produces the same output, so a
    regenerated fixture gives an empty diff rather than noise.
    """
    if counters is None:
        counters = {}
    if isinstance(data, dict):
        return {k: to_synthetic(v, k, counters, key) for k, v in data.items()}
    if isinstance(data, list):
        return [to_synthetic(v, key, counters, parent) for v in data]
    if isinstance(data, bool) or data is None:
        return data

    # Counted per (parent, key), not per key: a shared `name` counter was also
    # consumed by nested terms and users, so course names skipped pool entries
    # and started repeating.
    slot = f"{parent}.{key}"
    counters[slot] = counters.get(slot, 0) + 1
    n = counters[slot]
    if isinstance(data, str):
        return _synthetic_string(key, data, n, parent)
    if isinstance(data, int):
        return n if key.endswith("id") else 100 + n
    if isinstance(data, float):
        if key == "points_possible":
            return _POINTS[n % len(_POINTS)]
        if key in ("score", "entered_score"):
            return _SCORES[n % len(_SCORES)]
        return float(10 * n)
    return data


# --- demo mode ------------------------------------------------------------
#
# `--demo` serves the committed fixtures instead of the network. It is a
# transport swap, not a second implementation: the same client, filters, tools
# and scope registry run underneath. See `SCOPE.md` section 8.

FIXTURE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"

# The placeholder that stands in for a token in demo mode. Deliberately not a
# credential and deliberately obvious in any error message.
DEMO_TOKEN = "demo-mode-no-credential"

# Request path -> fixture file. Anything not listed 404s with a message saying
# demo mode is the reason, rather than looking like a Canvas failure.
DEMO_ROUTES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/api/v1/courses/?$"), "courses.json"),
    (re.compile(r"^/api/v1/courses/\d+/students/submissions/?$"), "submissions.json"),
)


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text())


def demo_transport() -> Any:
    """A transport that answers from `fixtures/` and never opens a socket."""
    import httpx2

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/api/v1/users/self":
            # Answered inline so the startup check runs in demo mode too,
            # rather than being skipped and going untested.
            return httpx2.Response(200, json={"id": 1, "name": "Demo Student"})
        for pattern, fixture in DEMO_ROUTES:
            if pattern.match(path):
                return httpx2.Response(200, json=load_fixture(fixture))
        return httpx2.Response(
            404,
            json={
                "message": f"{path} has no fixture; demo mode serves only "
                "the endpoints in DEMO_ROUTES."
            },
        )

    return httpx2.MockTransport(handler)

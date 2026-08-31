"""Checks that a fixture contains nothing real.

Fixtures ship inside a public repository, which makes them the one place live
API data could enter the repo — permanently, because removing a blob in a later
commit does not remove it from history. This module is the check that runs
before a fixture is written, and again in CI over everything already there.

Findings name the JSON path and the reason, never the offending value: a guard
that echoes a token into a CI log has leaked it just the same.
"""

import re
from datetime import date, timedelta
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
)
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


def _preserved(key: str, value: str) -> bool:
    """Whether an original string may be kept verbatim.

    Being on the allowlist is not enough: the value must also look like an
    enum. A field that unexpectedly carries free text is replaced anyway,
    otherwise the allowlist is a hole rather than an exception.
    """
    return key in PRESERVED_KEYS and bool(_ENUM_SHAPE.match(value))


def _synthetic_string(key: str, value: str, n: int) -> str:
    if _preserved(key, value):
        return value
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
        stamp = _BASE_DATE + timedelta(days=n)
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


def to_synthetic(data: Any, key: str = "root", counters: dict | None = None) -> Any:
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
        return {k: to_synthetic(v, k, counters) for k, v in data.items()}
    if isinstance(data, list):
        return [to_synthetic(v, key, counters) for v in data]
    if isinstance(data, bool) or data is None:
        return data

    counters[key] = counters.get(key, 0) + 1
    n = counters[key]
    if isinstance(data, str):
        return _synthetic_string(key, data, n)
    if isinstance(data, int):
        return n if key.endswith("id") else 100 + n
    if isinstance(data, float):
        return float(10 * n)
    return data

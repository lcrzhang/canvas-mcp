"""Checks that a fixture contains nothing real.

Fixtures ship inside a public repository, which makes them the one place live
API data could enter the repo — permanently, because removing a blob in a later
commit does not remove it from history. This module is the check that runs
before a fixture is written, and again in CI over everything already there.

Findings name the JSON path and the reason, never the offending value: a guard
that echoes a token into a CI log has leaked it just the same.
"""

import re
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

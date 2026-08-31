"""The guard that keeps real data out of the repository.

Two layers: unit tests that feed the detector known-bad documents, and a scan
over everything currently in fixtures/. The scan is what CI enforces; the unit
tests are what proves the scan can see anything at all.
"""

import json
from pathlib import Path

import pytest

from canvas_mcp.fixtures import find_real_looking_values

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_a_fully_synthetic_document_is_clean() -> None:
    document = {
        "id": 101,
        "name": "Introduction to Imaginary Systems",
        "uuid": "FIXTUREuuid0000000000000000000001",
        "calendar": {"ics": "https://canvas.example.edu/feeds/FIXTURE01.ics"},
        "teacher": {"email": "someone@example.edu"},
        "locked_for_user": True,
        "position": None,
        "items": [{"url": "https://canvas.example.edu/files/1?verifier=FIXTURE01"}],
    }
    assert find_real_looking_values(document) == []


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"ics": "https://canvas.uva.nl/feeds/x.ics"}, "real host"),
        ({"email": "docent@uva.nl"}, "real domain"),
        ({"url": "https://canvas.example.edu/f?verifier=1a2b3c"}, "verifier="),
        ({"token": "12345~abcdefghijklmnopqrstuvwxyz0123456789"}, "access token"),
        ({"uuid": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"}, "UUID"),
        ({"id": "0123456789abcdef0123456789abcdef"}, "hex string"),
    ],
)
def test_the_detector_sees_each_kind_of_real_value(
    document: dict[str, str], expected: str
) -> None:
    findings = find_real_looking_values(document)
    assert len(findings) == 1
    assert expected in findings[0]


def test_findings_name_the_path_and_never_the_value() -> None:
    secret = "12345~abcdefghijklmnopqrstuvwxyz0123456789"
    findings = find_real_looking_values({"a": [{"b": secret}]})
    assert findings == ["$.a[0].b: looks like a Canvas access token"]
    assert secret not in findings[0]


def test_nested_documents_are_walked() -> None:
    document = {"courses": [{"calendar": {"ics": "https://canvas.uva.nl/x.ics"}}]}
    findings = find_real_looking_values(document)
    assert findings[0].startswith("$.courses[0].calendar.ics:")


def test_every_committed_fixture_is_synthetic() -> None:
    """The check CI enforces. A no-op until step 3 adds the first fixture."""
    for path in sorted(FIXTURE_DIR.glob("*.json")) if FIXTURE_DIR.exists() else []:
        findings = find_real_looking_values(json.loads(path.read_text()))
        assert findings == [], f"{path.name} contains real-looking data: {findings}"

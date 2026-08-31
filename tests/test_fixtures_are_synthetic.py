"""The guard that keeps real data out of the repository.

Two layers: unit tests that feed the detector known-bad documents, and a scan
over everything currently in fixtures/. The scan is what CI enforces; the unit
tests are what proves the scan can see anything at all.
"""

import json
from pathlib import Path

import pytest

from canvas_mcp.fixtures import find_real_looking_values, to_synthetic

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


# --- conversion -----------------------------------------------------------

REAL_LOOKING = {
    "id": 60059,
    "name": "Datastructuren en Algoritmen",
    "course_code": "5062DAAL6Y",
    "uuid": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
    "workflow_state": "available",
    "is_public": False,
    "position": None,
    "created_at": "2025-09-01T08:30:00Z",
    "calendar": {"ics": "https://canvas.uva.nl/feeds/calendars/abc123.ics"},
    "teachers": [
        {"display_name": "Jan de Vries", "email": "j.devries@uva.nl", "id": 4471},
    ],
    "files": [
        {
            "url": "https://canvas.uva.nl/files/1/download?verifier=9f8e7d6c5b4a",
            "content_type": "application/pdf",
            "size": 10241,
        }
    ],
}


def shape_of(data: object) -> object:
    """Keys, nesting, list lengths and types — everything except values."""
    if isinstance(data, dict):
        return {k: shape_of(v) for k, v in data.items()}
    if isinstance(data, list):
        return [shape_of(v) for v in data]
    return type(data).__name__


def strings_in(data: object) -> list[str]:
    if isinstance(data, dict):
        return [s for v in data.values() for s in strings_in(v)]
    if isinstance(data, list):
        return [s for v in data for s in strings_in(v)]
    return [data] if isinstance(data, str) else []


def test_converted_output_passes_the_guard() -> None:
    assert find_real_looking_values(to_synthetic(REAL_LOOKING)) == []


def test_structure_survives_exactly() -> None:
    assert shape_of(to_synthetic(REAL_LOOKING)) == shape_of(REAL_LOOKING)


def test_no_original_string_survives_except_allowed_enums() -> None:
    converted = to_synthetic(REAL_LOOKING)
    survivors = set(strings_in(REAL_LOOKING)) & set(strings_in(converted))
    assert survivors == {"available", "application/pdf"}


def test_booleans_and_nulls_are_kept() -> None:
    converted = to_synthetic(REAL_LOOKING)
    assert converted["is_public"] is False
    assert converted["position"] is None


def test_an_enum_key_carrying_free_text_is_replaced_anyway() -> None:
    converted = to_synthetic({"type": "Uploaded by Jan de Vries on 2025-09-01"})
    assert "Jan de Vries" not in converted["type"]


def test_url_shapes_are_preserved_so_filter_tests_stay_meaningful() -> None:
    converted = to_synthetic(REAL_LOOKING)
    assert converted["calendar"]["ics"].endswith(".ics")
    assert "verifier=FIXTURE" in converted["files"][0]["url"]


def test_conversion_is_deterministic() -> None:
    assert to_synthetic(REAL_LOOKING) == to_synthetic(REAL_LOOKING)


def test_course_code_is_a_code_and_not_the_course_name() -> None:
    converted = to_synthetic(REAL_LOOKING)
    assert converted["course_code"] != converted["name"]
    assert converted["course_code"].startswith("FIX")

"""The guard that keeps real data out of the repository.

Two layers: unit tests that feed the detector known-bad documents, and a scan
over everything currently in fixtures/. The scan is what CI enforces; the unit
tests are what proves the scan can see anything at all.
"""

import json
from pathlib import Path

import pytest

from canvas_mcp.fixtures import (
    find_real_looking_values,
    load_fixture,
    shift_dates,
    to_synthetic,
)

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
        ({"email": "not-a-real-mailbox@uva.nl"}, "real domain"),
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
        {"display_name": "Jan de Vries", "email": "not-a-real-mailbox@uva.nl", "id": 4471},
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


def test_a_nested_name_is_named_for_what_it_is() -> None:
    """The same key means different things depending on its parent.

    Without this, a term and a user were both given course names, which reads
    as a broken tool rather than as sample data — a real reader said so within
    one sentence of seeing the demo.
    """
    document = {
        "name": "Datastructuren",
        "term": {"name": "Semester 1 2025-2026"},
        "user": {"name": "Jan de Vries"},
        "assignment": {"name": "Werkcollege 3"},
    }
    converted = to_synthetic(document)
    assert "Semester" in converted["term"]["name"]
    assert converted["user"]["name"] != converted["name"]
    assert converted["assignment"]["name"] != converted["name"]


def test_names_do_not_repeat_across_a_list_of_courses() -> None:
    """A counter shared with nested terms and users made course names skip
    entries in the pool and start repeating."""
    courses = [{"name": f"Course {i}", "term": {"name": f"Term {i}"}} for i in range(6)]
    names = [course["name"] for course in to_synthetic(courses)]
    assert len(set(names)) == len(names)


def test_a_score_never_exceeds_the_points_it_sits_next_to() -> None:
    document = {"score": 9.0, "points_possible": 10.0}
    converted = to_synthetic(document)
    assert converted["score"] <= converted["points_possible"]


def test_a_grade_reads_as_a_grade() -> None:
    converted = to_synthetic({"grade": "8.5"})
    assert "FIXTURE" not in converted["grade"]


def test_a_subheader_gets_a_section_name_not_a_file_name() -> None:
    """The parent passed down is a role, and only the item's own type says it
    labels a section rather than being material."""
    module = {
        "name": "Week 1",
        "items": [
            {"title": "Lectures", "type": "SubHeader"},
            {"title": "slides.pdf", "type": "File"},
        ],
    }
    items = to_synthetic(module, key="module")["items"]
    assert items[0]["title"] != items[1]["title"]
    assert items[0]["type"] == "SubHeader"


def test_loading_a_fixture_moves_its_dates_up_to_today() -> None:
    """The file keeps fixed dates so a regeneration diffs cleanly. Demo mode
    shifts them on load, so last year's capture is not an archived term."""
    from datetime import datetime, timedelta

    before = "2026-02-03T09:00:00Z"
    shifted = shift_dates({"due_at": before}, 400)
    moved = datetime.fromisoformat(shifted["due_at"]) - datetime.fromisoformat(before)
    assert moved == timedelta(days=400)


def test_shifting_leaves_everything_that_is_not_a_date_alone() -> None:
    document = {"name": "Week 1", "id": 3, "locked": True, "term": {"end_at": None}}
    assert shift_dates(document, 400) == document


def test_an_unparseable_date_survives_the_shift_unchanged() -> None:
    assert shift_dates({"due_at": "2026-13-45"}, 10)["due_at"] == "2026-13-45"


def test_the_demo_fixtures_are_current_when_loaded() -> None:
    """The check that would have caught the demo emptying itself."""
    from datetime import UTC, datetime

    from canvas_mcp.tools.courses import term_has_ended

    now = datetime.now(UTC)
    courses = load_fixture("courses.json")
    assert courses
    assert not any(term_has_ended(course, now) for course in courses)

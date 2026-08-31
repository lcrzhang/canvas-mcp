"""Capture a Canvas endpoint and write it out as a synthetic fixture.

Fetching, conversion and the guard all happen in one process, so the raw
response is never written to disk and never has to be cleaned up afterwards.
Nothing from the response is printed: the output is field names and counts,
which describe the schema rather than the data.

    python tools/make_fixture.py courses

Requires CANVAS_TOKEN in the environment. Not run in CI — CI has no token, and
should not have one.
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.fixtures import find_real_looking_values, to_synthetic

REPO_ROOT = Path(__file__).resolve().parent.parent


def richest_course(subpath: str, params: dict[str, Any]) -> Callable[..., str]:
    """Resolve a course-scoped path against the course that has the most data.

    Course ids are real data. Resolving one inside the process keeps it out of
    the source, out of the output and out of anyone's notes — the report says
    "course 3 of 6", never which course.

    Picking the richest course rather than the first matters: the first attempt
    at a submissions capture landed on a course with none, and an empty list
    tests nothing.
    """

    def resolve(client: CanvasClient) -> str:
        courses = list(
            client.paginate("/courses", params={"enrollment_state": "active"})
        )
        if not courses:
            raise CanvasError("No active courses to capture from.")

        best, best_count = None, 0
        for index, course in enumerate(courses, start=1):
            path = f"/courses/{course['id']}/{subpath}"
            found = list(client.paginate(path, params=params))
            print(f"  course {index} of {len(courses)}: {len(found)} items")
            if len(found) > best_count:
                best, best_count = path, len(found)

        if best is None:
            raise CanvasError(f"No {subpath} in any active course.")
        return best

    return resolve


# Every capture this project supports, so that what was fetched is readable
# rather than remembered. A path may be a string, or a function that resolves
# one against the live API.
# path/resolver, query parameters, and what one item in the response is. The
# third entry matters: the converter names a field after its parent, and a
# top-level object has none. Without it an assignment's `name` fell back to the
# course pool, and the demo listed course names where it meant assignments.
CAPTURES: dict[str, tuple[str | Callable[[CanvasClient], str], dict[str, Any], str]] = {
    "courses": (
        "/courses",
        {"enrollment_state": "active", "include[]": ["term"]},
        "course",
    ),
    # Enrollments carry the grades. Captured from /users/self rather than a
    # course, so no course id has to be written down here.
    "enrollments": ("/users/self/enrollments", {"state[]": ["active"]}, "enrollment"),
    # Per-assignment scores. Hidden final grades do not necessarily hide these.
    "submissions": (
        richest_course("students/submissions", {"student_ids[]": ["self"]}),
        {"student_ids[]": ["self"], "include[]": ["assignment"]},
        "submission",
    ),
    "assignments": (
        richest_course("assignments", {}),
        {"include[]": ["submission"], "order_by": "due_at"},
        "assignment",
    ),
}


def keys_in(data: Any) -> set[str]:
    if isinstance(data, dict):
        return set(data) | {k for v in data.values() for k in keys_in(v)}
    if isinstance(data, list):
        return {k for v in data for k in keys_in(v)}
    return set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", choices=sorted(CAPTURES))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    path_or_resolver, params, item_key = CAPTURES[args.capture]
    try:
        with CanvasClient() as client:
            path = (
                path_or_resolver(client)
                if callable(path_or_resolver)
                else path_or_resolver
            )
            raw = list(client.paginate(path, params=params))
    except CanvasError as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1

    fixture = to_synthetic(raw, key=item_key)

    findings = find_real_looking_values(fixture)
    if findings:
        print("Refusing to write: the guard found real-looking values.")
        for finding in findings[:20]:
            print(f"  {finding}")
        if len(findings) > 20:
            print(f"  ... and {len(findings) - 20} more")
        return 2

    out = args.out or REPO_ROOT / "fixtures" / f"{args.capture}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=2) + "\n")

    keys = sorted(keys_in(fixture))
    print(f"{len(raw)} objects from {args.capture}")
    print(f"{len(keys)} distinct keys, {out.stat().st_size} bytes written")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    print("keys: " + ", ".join(keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

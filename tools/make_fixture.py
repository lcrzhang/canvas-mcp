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
from pathlib import Path
from typing import Any

from canvas_mcp.client import CanvasClient, CanvasError
from canvas_mcp.fixtures import find_real_looking_values, to_synthetic

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every capture this project supports, so that what was fetched is readable
# rather than remembered.
CAPTURES: dict[str, tuple[str, dict[str, Any]]] = {
    "courses": ("/courses", {"enrollment_state": "active", "include[]": ["term"]}),
    # Enrollments carry the grades. Captured from /users/self rather than a
    # course, so no course id has to be written down here.
    "enrollments": ("/users/self/enrollments", {"state[]": ["active"]}),
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

    path, params = CAPTURES[args.capture]
    try:
        with CanvasClient() as client:
            raw = list(client.paginate(path, params=params))
    except CanvasError as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1

    fixture = to_synthetic(raw)

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
    print(f"{len(raw)} objects from {path}")
    print(f"{len(keys)} distinct keys, {out.stat().st_size} bytes written")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    print("keys: " + ", ".join(keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

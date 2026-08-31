# Roadmap — canvas-mcp

Status: **step 3 — fixtures and filter layer**

Order is 3b, 3a, 3: the guard checks the converter, the converter produces
the fixture, the fixture makes the filter tests mean something.

Scope and constraints live in `SCOPE.md`. Permission layers were established
empirically on 2026-08-29; see section 2 there before adding any endpoint.

---

## Legend

| Mark | Meaning |
|---|---|
| `[ ]` | not started |
| `[~]` | in progress — branch open, not merged |
| `[x]` | merged to main |
| `[-]` | dropped, with reason |

Steps marked **HUMAN** are written by Leo, not by the agent. The agent may
review them and write tests against them, but does not implement them.

---

## Milestone v0.1 — five read-only tools, no file content

### [x] 1. Repo scaffold and CI

**Delivers:** `pip install -e .` works, `pytest` runs, CI green on every PR.

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `CLAUDE.md`,
`.github/workflows/ci.yml`, `src/canvas_mcp/__init__.py`, `tests/test_import.py`

**Branch:** `chore/scaffold` · **Issue:** #1 · **PR:** #2 (merged, CI green)

**Notes:** `.gitignore` must contain `.env` before any token exists on disk.

Done during the step:

- The token predates the repo, so `.env` was left at `../.env`, outside the
  working tree. A mistake in `.gitignore` cannot leak it. `.env.example` is in
  the repo; `CLAUDE.md` records where the real one lives.
- "zero tests" was not viable: pytest exits 5 when it collects nothing, which
  fails CI. `tests/test_import.py` asserts the editable install and the src
  layout — exactly what this step delivers.
- No runtime dependencies declared. `httpx` belongs to step 2, the MCP SDK to
  step 5, each in that step's brief.
- No console-script entry point yet; it would point at `server:main`, which
  step 5 creates.
- CI runs a single Python 3.13 job. Add a 3.11 job when there is code that can
  break on it — a `requires-python` claim on an empty package proves nothing.

Affects later steps:

- `gh` is not installed and there is no git remote, so no issue or PR exists
  for this step. Every step from here inherits that until it is set up.

### [x] 2. HTTP client and error mapping

**Delivers:** `CanvasClient.get("/courses")` returns parsed JSON; a bad token
produces the actionable 401 message from SCOPE.md section 9.

**Files:** `src/canvas_mcp/client.py`, `tests/test_client.py`

**Branch:** `feat/client` · **Issue:** #5 · **PR:** #6 (merged)

**Notes:** startup check against `/users/self`, fail fast. Token from env only,
never a parameter.

Pagination moved to step 2b: together the diff was ~250 lines against a 150
line limit, and `get()` plus the error mapping stands alone as a reviewable
unit. Nothing before step 5 needs a second page.

`httpx2` was added here rather than `httpx`: the MCP SDK resolves to `httpx2`,
and two HTTP stacks in one project is not worth the familiarity of the older
name. Same API — `Client`, `MockTransport`, `Response.links`.

### [x] 2b. Pagination helper

**Delivers:** `CanvasClient.paginate("/courses")` yields every item, across
every page, following the `Link` header until there is no `rel="next"`.

**Files:** `src/canvas_mcp/client.py`, `tests/test_client.py`

**Branch:** `feat/pagination` · **Issue:** #7 · **PR:** #8 (merged)

**Notes:** inject `per_page` rather than trusting the default. `position` in
the modules response is **not** an index and must never be used as one — Canvas
filters unpublished items out of the response, so positions have gaps (see
`SCOPE.md` section 2).

Written during the step: yields items, not pages. Pages would push a second
loop into every caller for no gain. Params are sent on the first request only,
because the `rel="next"` URL already carries the query string. Stops with an
error after 50 pages rather than truncating: a silently short list is a
plausible wrong answer, which is the failure mode this project exists to avoid.

### [x] 3a. Fixture converter

**Delivers:** `to_synthetic(document)` rebuilds a live response with every
scalar value replaced, and a CLI that captures and converts in one process so
the raw response never reaches disk.

**Files:** `src/canvas_mcp/fixtures.py`, `tests/test_fixtures_are_synthetic.py`,
`tools/make_fixture.py`

**Branch:** `feat/fixture-converter` (**PR:** #12) and `feat/capture-courses`
(**PR:** #14) · **Issues:** #11, #13 — both merged

**Notes:** two PRs. The conversion function first, on its own, because it is
what stands between real data and a public repository. The CLI, the capture and
the resulting fixture second.

Replacement rather than redaction: a denylist fails on the field nobody thought
of, which is exactly the failure `SCOPE.md` section 5 documents. Structure is
preserved exactly so the filter tests still meet every field the live API
sends.

Captured on 2026-08-30: 6 active courses, 40 distinct keys, including the LTI
and admin plumbing section 5 of `SCOPE.md` predicted — `blueprint`, `template`,
`license`, `storage_quota_mb`, `grade_passback_setting`. Those are exactly the
fields a hand-written fixture would have missed.

Known wart: a term's `name` gets a course name from the pool, because the
converter keys on the field name and cannot see that it is nested under `term`.
Harmless for tests, odd to read. Fixing it needs parent context threaded
through the converter, which is a change to `to_synthetic`, not to this step.

`PRESERVED_KEYS` is the single exception, and it has a second gate: a value is
kept only if it also looks like an enum. The first version allowed spaces in
that shape, which let `Uploaded by <name> on <date>` survive under `type`. Enums
have no spaces; free text does. Caught by a test, not by review.

### [ ] 3. Fixtures and filter layer

**Delivers:** `slim_course()` turns the raw 4310-byte response into ~450 bytes;
tests assert that `calendar.ics`, `uuid` and any `verifier=` URL never survive.

**Files:** `src/canvas_mcp/filters.py`, `fixtures/courses.json`,
`tests/test_filters.py`

**Branch:** `feat/filters`

**Notes:** fixtures are captured by Leo with curl and converted to synthetic
values by hand — real field structure, invented values — before the agent sees
them. See `SCOPE.md` section 8. Every field Canvas returns stays in the fixture,
including unanticipated ones; only values change, and the hostname becomes
`canvas.example.edu`.

The byte counts in `SCOPE.md` section 5 are a one-off live measurement, not an
assertion: `test_filters.py` asserts that named fields are absent and that the
reduction is an order of magnitude, never `4310 → 450` exactly.

### [x] 3b. Fixture guard

**Delivers:** CI fails if anything in `fixtures/` looks like real data, and the
converter refuses to write a fixture the guard rejects.

**Files:** `src/canvas_mcp/fixtures.py`, `tests/test_fixtures_are_synthetic.py`

**Branch:** `test/fixture-guard` · **Issue:** #9 · **PR:** #10 (merged)

**Notes:** scans every fixture for `uva.nl` hostnames and e-mail addresses, for
`verifier=` values without the `FIXTURE` prefix, and for hex strings of token
length. Turns "Leo remembered to anonymise it" into an assertion — the same
argument this project makes about scopes: enforce it, do not document it.

Numbered 3b rather than renumbering, because steps 4 and 13 are referred to by
number in `CLAUDE.md`.

Reordered to run **before** step 3. The earlier plan put it after, on the
argument that a test with nothing to scan proves nothing. That was wrong once
the fixtures became the output of a converter: the guard is the check on that
converter and has to exist first. The detector is unit-tested against known-bad
documents, so it is proven without any fixture present.

The detector lives in `src/canvas_mcp/fixtures.py` rather than in the test,
because the converter imports it too — and step 11's demo loader belongs in the
same module.

### [ ] 4. Scope registry — **HUMAN**

**Delivers:** deny-by-default tool registration; `--scopes courses:read` exposes
exactly one tool; an unregistered scope raises at startup, not at call time.

**Files:** `src/canvas_mcp/scopes.py`

**Branch:** `feat/scopes`

**Notes:** this is the learning goal of the project. `grades:read` exists but is
off by default — that gap between what the token allows and what the server
allows is the point.

### [ ] 5. MCP server and `list_courses`

**Delivers:** the server runs in Claude Desktop and answers "which courses am I
taking?" against the real API.

**Files:** `src/canvas_mcp/server.py`, `src/canvas_mcp/tools/courses.py`

**Branch:** `feat/list-courses`

**Notes:** first end-to-end step. Resolve `enrollment_term_id` to a term name
via `include[]=term` — a bare `417` is useless to a model.

### [ ] 6. `list_assignments`

**Delivers:** "what is due this week for Datastructuren?" works.

**Files:** `src/canvas_mcp/tools/assignments.py`, tests

**Branch:** `feat/list-assignments`

**Notes:** `due_at` may be null. `only_upcoming` filters on it; document what
happens to assignments without a due date rather than dropping them silently.

### [ ] 7. Sanitizer

**Delivers:** teacher HTML becomes plain text, capped, with an explicit
`[truncated]` marker and visible delimiters around untrusted content.

**Files:** `src/canvas_mcp/sanitize.py`, `tests/test_sanitize.py`

**Branch:** `feat/sanitize`

**Notes:** test with a fixture containing an injection attempt. The README must
state that this mitigates, not solves — the real defence is the absence of
write tools.

### [ ] 8. `get_assignment`

**Delivers:** "what is the week 1 assignment about?" works, sanitized.

**Branch:** `feat/get-assignment`

### [ ] 9. `list_announcements`

**Delivers:** recent announcements per course, plain text.

**Branch:** `feat/list-announcements`

### [ ] 10. `list_materials`

**Delivers:** "which slides belong to week 1?" works. Module tree flattened to
module → subheader section → items.

**Files:** `src/canvas_mcp/tools/materials.py`, `fixtures/modules.json`

**Branch:** `feat/list-materials`

**Notes:** `SubHeader` items are labels, not content — group following items
under them by `indent`. Respect `locked_for_user` and `hidden_for_user`. The
course file index is 403 for students; modules are the only way in.

### [ ] 11. Fixture mode

**Delivers:** `canvas-mcp --demo` runs with no token and no network.

**Branch:** `feat/demo-mode`

**Notes:** a transport that reads `fixtures/` instead of the network, not a
second implementation — `CanvasClient` already takes `transport=`, which is the
only reason this step is small enough to be worth doing.

It exists for the reader, not the user: anyone evaluating this repo has no UvA
account and would otherwise have to take the README's claims on trust. Token
expiry is not the argument; see `SCOPE.md` section 8.

### [ ] 12. README and v0.1.0

**Delivers:** tagged release. README leads with non-goals, the permission-layer
findings, and the measured raw-vs-filtered byte counts.

**Branch:** `docs/readme`

**Notes:** the argumentation here is Leo's — the agent may draft structure, not
claims.

### [ ] 13. Tool description pass — **HUMAN**

**Delivers:** empirical check that the model picks the right tool. Iterate on
descriptions until it does.

**Notes:** no code, only descriptions. Roughly 30% of the project's value and
the part that cannot be delegated: the failure mode is a plausible wrong
answer, not an exception.

---

## Milestone v0.2 — file content

### [ ] 14. `read_file` with page ranges

**Delivers:** "what is on slides 10-15 of lec01_intro?" works.

**Notes:** extraction sits behind one function,
`extract_text(path, pages) -> str`, so the backend stays swappable. Hard size
cap; refuse above it with a clear error. A page with no text layer returns
empty — detect that and say so rather than returning nothing.

---

## Backlog

- `list_grades` as a documented, off-by-default example — depends on step 4
- caching — currently a non-goal; revisit only if `read_file` proves too slow

---

## Dropped

- `list_files` via `/courses/:id/files` — returns 403 for student tokens;
  replaced by `list_materials` via the module tree
- OCR — permanently out of scope, drags in ML dependencies for marginal gain
- Marker / MinerU as extraction backend — better fidelity, but turns a small
  project into an installation project

# Roadmap — canvas-mcp

Status: **step 11 merged early** — demo mode, and the server confirmed working in a real client on 2026-08-31

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

### [x] 3. Filter layer

**Delivers:** `slim_course()` reduces a raw course by an order of magnitude;
tests assert that `calendar.ics`, `uuid` and any `verifier=` URL never survive.

**Files:** `src/canvas_mcp/filters.py`, `tests/test_filters.py`

**Branch:** `feat/filters` · **Issue:** #17 · **PR:** #18 (merged)

**Notes:** the fixture moved to step 3a, which automated the capture — it is no
longer converted by hand, and the raw response reaches neither disk nor the
agent. See `SCOPE.md` section 8.

The byte counts in `SCOPE.md` section 5 are a one-off live measurement, not an
assertion: `test_filters.py` asserts that named fields are absent and that the
reduction is an order of magnitude, never `4310 → 450` exactly. Measured 11.2x
on the six-course fixture, against ~9x on the live four-course response.

Built as an **allowlist**, which section 5 does not say. Section 5 reads as a
list of fields to remove, and a denylist has to be complete to be correct — the
capture on 2026-08-30 confirmed the response carries fields nobody predicted.
Building the output from named fields is wrong in the safe direction: a field
nobody thought of is missing rather than leaked. The per-field tests section 5
asks for are still there, and are what fails if the allowlist is widened.

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

### [x] 4. Scope registry — design **HUMAN**

**Delivers:** deny-by-default tool registration; `--scopes courses:read` exposes
exactly one tool; an unregistered scope raises at startup, not at call time.

**Files:** `src/canvas_mcp/scopes.py`

**Branch:** `test/scopes` · **Issue:** #19 · **PR:** #20 (merged)

**Notes:** this is the learning goal of the project. `grades:read` exists but is
off by default — that gap between what the token allows and what the server
allows is the point.

Designed together on 2026-08-30; `tests/test_scopes.py` is the specification
and was written first. Decisions taken, each with the reason in one line:

| Decision | Choice | Why |
|---|---|---|
| a tool outside scope | not registered, invisible | a forgotten registration is an annoyance, a forgotten check is a leak |
| where the scope lives | one table in `scopes.py` | the policy fits on a page and can be pointed at |
| preventing drift | the constructor refuses | table and tools must match or the server does not start |
| unknown scope name | raises at construction | a typo must not yield a silently empty server |
| the default | an explicit list, not "everything except" | growing the default becomes a decision, and the README cannot drift |
| wildcards | none | `courses:*` is "everything except" turned around |
| who filters | the registry hands out tools | `server.py` cannot register what it was never given |

Rejected: a call-time `require()` inside each tool. It gives better
observability — you can log what was attempted — but one forgotten line is a
leak, and there is no logging in this project to make the benefit real.

This is the same move as the fixture guard and the filter allowlist: enforce
it, do not trust it.

The tests were written first and the implementation followed. Leo made every
decision in the table above; writing the code was delegated once the design was
settled, on the grounds that the reasoning was the learning goal, not the
typing. `CLAUDE.md` records that split.

**Found while planning step 5, and resolved.** `TOOL_SCOPES` lists all six v0.1
tools, and the first version of the registry also refused to start when a table
row had no matching tool. At step 5 only two tools exist, so the server could
not have started at all.

Resolved by splitting the check by consequence rather than by symmetry:

- **a tool with no policy row** could run unpoliced — a leak. Stays enforced at
  construction.
- **a policy row with no tool** is stale documentation. Moved to the test
  suite, which runs on every PR and can see every tool once they exist.

Building the tools one step at a time now works, and a renamed tool is still
caught. Same principle as everywhere else, applied at the right layer: enforce
what prevents damage, assert what guards documentation.

### [x] 5. MCP server, `list_courses` and `list_grades`

**Delivers:** the server runs in Claude Desktop and answers "which courses am I
taking?" against the real API.

**Files:** `src/canvas_mcp/server.py`, `src/canvas_mcp/tools/courses.py`

**Branch:** `feat/list-courses` (**PR:** #22), `feat/list-grades` (#23), `feat/list-grades-tool` (5b) · **Issue:** #21

**Notes:** first end-to-end step. Resolve `enrollment_term_id` to a term name
via `include[]=term` — a bare `417` is useless to a model.

`list_grades` is built here too, alongside `list_courses`. It was in the
backlog; moving it forward makes the demonstration real at the earliest
possible moment — two tools registered, one visible, one not, and the second
appears only when someone types `grades:read`. That is the project's claim,
runnable, from the first step that runs.

Also add the test that step 4 moved out of the runtime: every row in
`TOOL_SCOPES` names a tool that actually exists.

Print one line at startup naming the enabled and disabled scopes. Diagnostics,
not logging — no request data, nothing near a token.

Split into two PRs: 5a is the server, the CLI and `list_courses`; 5b is
`list_grades` and the table test.

**5b is blocked by an empirical finding, 2026-08-31.** Before writing
`list_grades` the endpoints were captured, the way section 2 of `SCOPE.md`
demands. Result: this token cannot read grades at all. The `grades` object in
an enrollment carries only `html_url`; `current_score`, `current_grade`,
`final_score` and `final_grade` are absent rather than null, and
`include[]=total_scores` on `/courses` adds nothing. The courses carry
`hide_final_grades: true`.

So the intended claim — the token may read grades, this server may not — is
false on canvas.uva.nl. Canvas blocks it before this server gets the chance.

Three ways forward, and it is Leo's decision:

1. **Drop `list_grades` and `grades:read`.** The scope machinery is proven by
   its own tests either way; the README needs a different example.
2. **Keep `list_grades` returning only the grades page URL.** It demonstrates
   the mechanism — off by default, appears when enabled — but returns almost
   nothing, which is a weak thing to build a README around.
3. **Test whether per-assignment submission scores are readable.** Hidden final
   grades do not necessarily hide individual submission scores, and "what did I
   score on this assignment" is both useful and sensitive. If it works, the
   demonstration survives intact and gets better. Needs one more capture, and
   a capture keyed on a course id rather than a fixed path.

**Chosen: 3, and it works.** `GET /courses/:id/students/submissions` with
`student_ids[]=self` returns `score`, `grade`, `entered_score`,
`points_possible`, `graded_at`, `late`, `missing` and `excused`. So
`list_grades` becomes per-assignment scores for one course — a better
demonstration than course totals would have been: more useful to a student, and
more clearly something a server should gate.

The capture needed a course id, which is real data. `course_with_submissions()`
resolves one inside the process and reports "course 3 of 6", never which course,
and picks a course that actually has submissions — a fixture of an empty list
tests nothing.

`fixtures/submissions.json` is 91363 bytes for 12 submissions across 129
fields, including `secure_params`, `preview_url` and every assignment's full
`description`. It is the strongest case in the repo for the filter layer.

`fixtures/enrollments.json` stays uncommitted: it produced a finding, but no
test uses it. The capture entry remains, so it is one command away.

**5b delivered.** `slim_submission()` is an allowlist of six fields, and the
reduction is **40x** — 64044 bytes of submissions to 1612. That is the largest
measurement in the project and the clearest answer to why section 5 exists.

`flags` is a list naming only what is true, rather than three booleans that are
usually false. `course_id` passes through `int()` before it reaches a path: the
SDK validates the type from the hint, but that argument is model-chosen and one
coercion closes it at the source.

The check step 4 moved out of the registry now lives in
`test_every_policy_row_names_a_tool_that_exists_or_is_listed_as_pending`, with
a `NOT_YET_BUILT` set covering steps 6 to 10. Adding a tool fails that test
until its name is removed, so the list tracks the remaining work and the check
does real work today. Together they were ~350 lines against a 150
line limit. 5a alone is ~200 and still over, but splitting the server from its
first tool would produce a branch that cannot be run at all, and this step is
defined by being runnable.

**mcp 2.x, not 1.x.** `FastMCP` was renamed `MCPServer`, the API is snake_case
(`input_schema`, `read_only_hint`) and `list_tools()` is a coroutine. Verified
against the installed package rather than assumed, which is the second time
that has changed a decision here — `httpx2` was the first.

Tools are built by factories that close over the client rather than taking one
as an argument. Tool arguments are chosen by a model; a `client` parameter
would put the connection, and through it the token, inside something the model
can influence.

The startup line goes to **stderr**. The stdio transport speaks the protocol on
stdout, so a stray print there corrupts the stream — a failure that looks like
a broken server rather than a broken print. There is a test for it.

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

### [~] 11. Fixture mode

**Delivers:** `canvas-mcp --demo` runs with no token and no network.

**Branch:** `feat/demo-mode` · **PR:** #25

**Notes:** a transport that reads `fixtures/` instead of the network, not a
second implementation — `CanvasClient` already takes `transport=`, which is the
only reason this step is small enough to be worth doing.

It exists for the reader, not the user: anyone evaluating this repo has no UvA
account and would otherwise have to take the README's claims on trust. Token
expiry is not the argument; see `SCOPE.md` section 8.

**Pulled forward from after step 10**, for a reason nobody wrote down: it makes
the server testable end to end without a token. `tests/test_end_to_end.py`
starts `canvas_mcp.server` as a real subprocess and speaks the protocol over
stdio — initialize, list tools, call one. Every other test exercises a module;
this is the difference between "the parts work" and "the server serves". The
alternative was an in-memory harness coupled to the SDK's private
`_lowlevel_server`.

`/users/self` is answered inline so the startup check runs in demo mode too,
rather than being skipped and going untested. The base URL becomes
`canvas.example.edu`, so demo output never names a real institution for a
request that was never made.

**Found here: the HTTP library logs every request URL at INFO**, which under
stdio lands in the client's log file. Section 7 lists logging as a non-goal and
that has to hold for dependencies; a Canvas URL can carry a `verifier=`.
`quiet_http_logging()` drops those to WARNING.

**Confirmed in Claude Desktop on 2026-08-31.** Both tools registered, both
called, the protocol handshake completed, the `instructions` string delivered.
First attempt, no changes needed.

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

Found during the live test on 2026-08-31: the generated schema for
`list_courses` is `{"term_filter": {}}` — no type at all, while `course_id`
correctly gets `{"type": "number"}`. A `str | None` annotation produces an
empty schema, so a model is told nothing about what it may pass. Schemas belong
with descriptions: both are what a model reads before choosing.

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

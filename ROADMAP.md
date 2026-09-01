# Roadmap — canvas-mcp

Status: **step 12 — README and v0.1.0**

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

**Fixed on 2026-08-31, after the live test.** The wart was that a term's
`name` got a course name, because the converter keyed on the field name and
could not see it was nested under `term`. It was recorded here as harmless.

It was not. The first reader of the demo said "term and name seem to be mixed
up" within one sentence, and concluded the tool was confused rather than the
data. Demo mode exists to convince a reader (`SCOPE.md` section 8), so the
quality of that data is load-bearing, not cosmetic. The evidence changed and
the judgement with it.

`to_synthetic` now carries the parent key, so `name` resolves against terms,
users, assignments or courses. Counters are kept per `(parent, key)` rather
than per key: a shared `name` counter was also consumed by nested terms and
users, which made course names skip pool entries and repeat. Grades became
letters, so nothing invites a reader to check whether `grade` and `score`
agree — independent counters cannot promise that. Scores draw from a range
below the smallest `points_possible`, so a score never exceeds its maximum.

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

**Notes (after the live test, 2026-08-31):** `current_only` was added to
`list_courses` and defaults to true. `enrollment_state=active` means the
enrolment is active, not that the term is running, so Canvas returned six
courses of which three came from terms that ended in 2024 and 2025. The model
sorted it out from the term names, but only because they happened to carry the
year — and it should not have had to. Step 6 would have inherited the problem
as "what is due this week" searching courses from two years ago.

A term with no end date counts as running, and an unparseable date never hides
a course: erring towards showing too much is the safe direction here.

That change also broke the demo, which is how the fixture's dates were found to
be stale — every synthetic term had already ended. Fields meaning "this closes
later" are now dated a year past the base date.

**Done properly on 2026-09-01.** `load_fixture` shifts every date forward by the
distance from the fixture's base date to today. The file keeps fixed dates, so
regenerating still diffs cleanly, and the demo cannot quietly empty itself once
the clock moves past them. A test asserts the committed courses are in running
terms when loaded — the check that would have caught it the first time.

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

### [x] 6. `list_assignments`

**Delivers:** "what is due this week for Datastructuren?" works.

**Files:** `src/canvas_mcp/tools/assignments.py`, tests

**Branch:** `feat/list-assignments` · **Issue:** #29 · **PR:** #30 (merged)

**Notes:** `due_at` may be null. `only_upcoming` filters on it; document what
happens to assignments without a due date rather than dropping them silently.

Done: an assignment with no due date counts as upcoming and is always returned.
There is no date on which to decide it is over, and hiding work that still has
to be done is the wrong direction to err in. Same for an unparseable date.

`only_upcoming` defaults to **false**, unlike `current_only` on `list_courses`.
The difference is what the model has to infer. A finished term could only be
recognised from a term name; a passed deadline is a date sitting in the output,
which a model can filter exactly. Nothing is hidden and nothing has to be
guessed.

`submitted` is None rather than False when the response carried no submission
object. Claiming "not handed in" on missing information is precisely the
plausible wrong answer this project exists to avoid.

**Scope question raised here:** `locked_for_user` was true on seven of twelve
assignments, including ones already submitted. `SCOPE.md` section 5 said a
locked item does not exist for the tool; applied literally that hides most of
the deadlines, and a missed deadline is exactly what a student needs to see.
Section 5 now distinguishes: `hidden_for_user` drops the item, `locked_for_user`
becomes a field. The original reading still holds for files and modules in step
10, where locked really does mean the content is off limits.

Captures gained an item key, because the converter names a field after its
parent and a top-level object has none: an assignment's `name` fell back to the
course pool, so the demo listed course names where it meant assignments. Same
defect class as the one the live test surfaced on 2026-08-31, in a new place.

### [x] 7. Sanitizer

**Delivers:** teacher HTML becomes plain text, capped, with an explicit
`[truncated]` marker and visible delimiters around untrusted content.

**Files:** `src/canvas_mcp/sanitize.py`, `tests/test_sanitize.py`

**Branch:** `feat/sanitize` · **Issue:** #31 · **PR:** #32 (merged)

**Notes:** test with a fixture containing an injection attempt. The README must
state that this mitigates, not solves — the real defence is the absence of
write tools.

The injection sample is a test constant rather than a captured fixture. A
capture would not contain one, and writing it deliberately is the point: the
test asserts the attempt arrives **intact and visible**, not that it was
filtered. Filtering it would be the dangerous move, because it would suggest
the problem had been handled.

**The delimiters are the part that had to be got right.** Content that contains
the closing delimiter could otherwise end the untrusted section early and have
whatever followed read as though the server had said it. Both markers are
stripped from the body before wrapping, with a test for each.

No dependency added: `html.parser` from the standard library does the work.
Links are kept as `text (url)` — a description reading "see the link" tells a
model nothing without it.

The cap reports how much was cut rather than trailing off, so a model can say
the text was shortened instead of answering from half of it.

### [x] 8. `get_assignment`

**Delivers:** "what is the week 1 assignment about?" works, sanitized.

**Branch:** `feat/get-assignment` · **Issue:** #33 · **PR:** #34 (merged)

**Notes:** `slim_assignment_detail` is a second function rather than a flag on
`slim_assignment`. The list view must never carry a description, and a boolean
parameter is easier to get wrong than two names.

A missing description comes back as None, not as an empty pair of delimiters.
Empty delimiters would say "there is content here" when there is not, which is
a small lie a model would repeat.

The test that the detail view withholds everything the list view does had to
exclude `description` — which is the point of the step, and now written down as
one line instead of implied.

Demo routes gained id selection, so `/courses/N/assignments/M` serves the
matching item from the list fixture. The converter's stand-in for teacher HTML
became three realistic bodies with markup, an entity and a link, so the demo
shows the sanitizer doing work rather than echoing a placeholder.

### [x] 9. `list_announcements`

**Delivers:** recent announcements per course, plain text.

**Branch:** `feat/list-announcements` · **Issue:** #35 · **PR:** #36 (merged)

**Notes:** captured on 2026-09-01 via `discussion_topics?only_announcements`.
One course returned **104 announcements, 247539 bytes across 79 fields**. The
default limit is 10 and the ceiling is 50, in the tool rather than in the
caller's judgement: each announcement costs a model its whole sanitized body.

The author is left out. `author`, `user_name`, `pronouns` and
`avatar_image_url` are a third party's identity, and none of it is needed to
answer "are there new announcements". Section 3 asked for title, date and body,
and that is what it returns.

Sorted newest first in the tool rather than trusting the API's order, with
undated announcements last. Same reasoning as not relying on `order_by=due_at`
in step 6.

Reduction is **5.9x**, far below the 40x of assignments and submissions —
because here the body *is* the content, so there is little to remove. The
delimiters cost about 130 bytes per item, which is most of what the wrapper
adds and another reason the default limit is small.

### [x] 10. `list_materials`

**Delivers:** "which slides belong to week 1?" works. Module tree flattened to
module → subheader section → items.

**Files:** `src/canvas_mcp/tools/materials.py`, `fixtures/modules.json`

**Branch:** `feat/list-materials` · **Issue:** #37 · **PR:** #38 (merged)

**Notes:** `SubHeader` items are labels, not content — group following items
under them by `indent`. Respect `locked_for_user` and `hidden_for_user`. The
course file index is 403 for students; modules are the only way in.

**Grouping is sequential, not by indent.** A SubHeader opens a section and
everything after it belongs there until the next one. `indent` is how deeply
Canvas draws an item, not what it belongs to; using it for membership would
misplace an item the moment a teacher indents something for looks. The note
above asked for "group following items under them", and that is what this does.

**Closed on 2026-09-01.** The first capture picked the course with the most
items, which happened to use no SubHeader at all. Probing every active course
found four in one and one in another. The resolver now prefers a course that
uses them, and the grouping is verified against real data: four named sections
in one module, and items before the first subheader in a nameless one.

Worth remembering as a capture rule — the richest course is not the most
representative one, and "the feature has no example in the fixture" is easy to
mistake for "the feature is fine".

**Neither `locked_for_user` nor `hidden_for_user` appears on a module.** Canvas
filters on enrolment before the response is built — the same finding section 2
of `SCOPE.md` records for module positions. A module's `state` carries `locked`
instead, and a locked module keeps its name and loses its contents: hiding it
entirely would hide the shape of the course, which is not what is being
protected.

**Items report `content_id`, not their own id.** That is what `read_file` needs
in v0.2, and modules are the only place it can come from. `SCOPE.md` section 3
says the output is name and type; the id is a third field, added because
without it step 14 has no way to name a file.

The converter had to stop renumbering `indent` — it is structure, not identity,
and a counter in its place makes the tree meaningless. Module names and item
titles got their own pools, so the demo reads as a course rather than as a list
of course names.

### [x] 11. Fixture mode

**Delivers:** `canvas-mcp --demo` runs with no token and no network.

**Branch:** `feat/demo-mode` · **Issue:** #25 · **PR:** #26 (merged)

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

### [x] 12. README and v0.1.0

**Delivers:** tagged release. README leads with non-goals, the permission-layer
findings, and the measured raw-vs-filtered byte counts.

**Branch:** `docs/readme`

**Notes:** the argumentation here is Leo's — the agent may draft structure, not
claims.

**Delegated on 2026-09-01**, after every claim had been measured or captured.
The rule it replaces was there so nothing would be asserted that had not been
checked; by this point each line traces to something observed — the reduction
table to `fixtures/`, the permission table to section 2, the demonstration to
the checklist above. `CLAUDE.md` records the split.

Leads with non-goals, as the note required. Two things it says that a README
would usually leave out:

*The demonstration is stated in its corrected form.* "The token may read grades,
this server may not" is false for course grades on canvas.uva.nl — Canvas hides
them first. The README says so, and puts the demonstration where it actually
holds: per-assignment scores, which the token can read and the server will not
without `grades:read`.

*The reduction table keeps its low numbers.* 4.3x for modules next to 48.8x for
assignments, with the reason: where the payload is the content there is little
to remove. A table showing only the large factors would be selling something.

`LICENSE` added — `pyproject.toml` claimed MIT with no file to back it.

### [x] 13. Tool description pass

**Delivers:** empirical check that the model picks the right tool. Iterate on
descriptions until it does.

**Notes:** no code, only descriptions. Roughly 30% of the project's value and
the part that cannot be delegated: the failure mode is a plausible wrong
answer, not an exception.

**Correction, 2026-09-01.** This step recorded a schema defect: that
`list_courses` generated `{"term_filter": {}}` with no type. That was wrong.
The claim came from a tool listing rendered by a client, not from the server,
and `MCPServer` generates `{"anyOf": [{"type": "string"}, {"type": "null"}],
"default": null}` — which is correct. A bug was reported on the strength of a
rendering, without checking the source. `tests/test_tool_contract.py` now
asserts the property that was assumed broken, so it stays true.

**Done, 2026-09-01.** Every description was rewritten around the question a
model has to answer before calling: *which of these six*. The first line of
each is now the question it answers rather than a summary of its output, and
overlapping pairs point at each other — `list_assignments` sends content
questions to `get_assignment` and material questions to `list_materials`;
`list_materials` says assignments appear there too but deadlines belong
elsewhere.

Every tool gained a human-readable `title`. The function name is what the model
reads; the title is what a person sees in their client's tool list.

**What could not be delegated, and is still open.** The roadmap always said
this step is an empirical check that the model picks the right tool. Rewriting
the descriptions is not that check. The failure mode is a plausible wrong
answer, which no test can see, so it has to be run against a real client:

| Ask | Should call | Wrong answer looks like |
|---|---|---|
| "what do I have to do for X this week" | `list_assignments` | listing modules, or every deadline including past ones |
| "what does the week 3 assignment ask" | `list_courses` → `list_assignments` → `get_assignment` | answering from the title alone |
| "where are the slides for week 3" | `list_materials` | `list_assignments`, because slides are attached to one |
| "did they say anything about the exam" | `list_announcements` | searching assignment descriptions |
| "how am I doing in X" | refusal, or `list_grades` if enabled | estimating a course grade from assignment scores |
| "what did I take last year" | `list_courses(current_only=false)` | "you are taking nothing", from the filtered list |

Run each, note what it called, and change the description of whichever tool it
should have picked.

**First result, 2026-09-01 — the grades question.** With `grades:read` off, a
model asked for scores searched its tool list, found nothing, and said so
without estimating or retrying. That is the behaviour the invisible-over-
forbidden choice was made for, now observed rather than argued.

But it explained the absence as *"this server is still being built, there is no
tool for scores yet"*. The tool exists and is switched off, and a model cannot
tell the difference — that is inherent to not registering it. So it filled the
gap with something plausible and wrong, which is precisely this project's named
failure mode, arriving in the one place no test was looking.

Fixed in the server `instructions` rather than in a tool description: the
server now states that anything missing is missing by configuration, that a
model should say so rather than guess why, and that it must not estimate the
answer a missing tool would have given. It does not say *what* is missing —
that would undo the choice — and the string is identical whatever is enabled,
so its length cannot be read as a hint.

**A configuration mistake found alongside it.** The setup instructions written
on 2026-08-31 pinned `--scopes courses:read,grades:read`, so removing grades
left a single tool and four of the six had never run in a real client at all.
The default scope set exists exactly so that nobody has to write one; the
instructions should have omitted the flag.

**Full checklist, 2026-09-01, against two live courses. Six of six.** Every
question reached the tool it should have. Two results are worth keeping:

*The grades question did not produce a grade.* Holding submission status and
points per assignment, the model reported what was handed in and said plainly
that no grade overview is available through these tools. Estimating one was
available to it and it did not.

*The deadline question called five tools where two would have done* — courses,
assignments, announcements, materials twice, then one assignment. Left alone:
the extra breadth surfaced a rule from the welcome announcement that belonged
in the answer, and a description discouraging that would trade a better answer
for fewer calls.

**A wrong diagnosis, recorded because it is the second today.** Two filtered
calls returned nothing — `module_filter="week 2"` and `"week 1"` — and this was
written up as a broken filter. It was not: one course has no week 2 module
published, the other organises its modules differently. The filter was correct
and the model drew the right conclusion both times. Together with the schema
claim, that is twice a defect was reported from an indirect reading rather than
from the source, in a project whose method is checking the source.

What it did show is a missing sentence: an empty filtered result is
indistinguishable from an empty course, so both filters now say so and tell the
caller to retry without one.

*Also confirmed on live data:* subheader sectioning works on a course other
than the fixture — four named sections in one module, items before the first
heading in a nameless one — and module items carry real file ids, which is what
step 14 needs.

---

## Milestone v0.2 — file content

### [~] 14. `read_file` with page ranges

**Delivers:** "what is on slides 10-15 of lec01_intro?" works.

**Notes:** extraction sits behind one function,
`extract_text(path, pages) -> str`, so the backend stays swappable. Hard size
cap; refuse above it with a clear error. A page with no text layer returns
empty — detect that and say so rather than returning nothing.

Split into 14a and 14b: the extraction layer, which needs no network, and then
the fetch and the tool. Together they are ~270 lines.

**14a done, 2026-09-01.** `pypdf`, chosen over PyMuPDF: PyMuPDF extracts better
and is AGPL, which the repository cannot take on now that it is public. It
takes bytes rather than a path, so nothing has to be written to disk to be
read.

The signature moved from `extract_text(path, pages)` to `extract_text(data,
pages)` for that reason. `page_count` joins it as the second and last function
that knows what a PDF is.

Page ranges are one-based and inclusive, because that is what is printed on the
page and what a student types. A range running past the end stops at the end; a
range starting past it is an error naming the real length. Asking for more than
20 pages is refused — beyond that it is a request for a document rather than a
passage, and the answer would be truncated anyway.

A page with no text layer beside one with text is marked `[page 2] no text`
rather than dropped. A document with no text at all is refused, and the error
says it is probably a scan and that this server does not do OCR. Silence would
read as "the page is blank" about a page full of scanned writing.

**No PDF fixture.** The tests assemble a minimal PDF whose text they already
know, which proves more than a captured one and keeps a teacher's slides out of
the repository. Empty page contents give a page with no text layer, which is
what a scan looks like from here.

**14b done, 2026-09-01.** The builder moved from the tests into `fixtures.py`,
because demo mode needs a document too and committing one would mean either a
binary nobody can review or a teacher's real slides.

Size is checked twice: against `Content-Length` before the body is transferred,
and against what actually arrived. Content-Length is a claim, not a promise,
and a server understating it should not be able to spend a caller's memory.

For a file, `locked_for_user` refuses — the strict reading of section 5, which
is where it belongs. On an assignment in step 6 it became a field instead. The
same flag, two meanings, and the difference is whether it withholds content.

**The default scope list grew, and had to break a test to do it.** Adding
`files:content` to `DEFAULT_SCOPES` failed the step 4 specification, which
named four scopes. That is exactly why the default is a written list rather
than "everything except `grades:read`": a rule would have absorbed the new
scope silently, and nobody would have decided anything. Reading a slide is what
a study assistant is for and the file is one the student can already open, so
it is on by default — but that is a decision, taken in a pull request, and
reversible by moving one line.

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

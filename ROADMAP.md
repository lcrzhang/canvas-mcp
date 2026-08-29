# Roadmap — canvas-mcp

Status: **step 1 — repo scaffold** · branch `chore/scaffold` open, not merged

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

### [~] 1. Repo scaffold and CI

**Delivers:** `pip install -e .` works, `pytest` runs, CI green on every PR.

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `CLAUDE.md`,
`.github/workflows/ci.yml`, `src/canvas_mcp/__init__.py`, `tests/test_import.py`

**Branch:** `chore/scaffold`

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

### [ ] 2. HTTP client and error mapping

**Delivers:** `CanvasClient.get("/courses")` returns parsed JSON; a bad token
produces the actionable 401 message from SCOPE.md section 9.

**Files:** `src/canvas_mcp/client.py`, `tests/test_client.py`

**Branch:** `feat/client`

**Notes:** startup check against `/users/self`, fail fast. Token from env only,
never a parameter. Pagination helper (`per_page`, Link header) belongs here —
`position` in the modules response is not an index.

### [ ] 3. Fixtures and filter layer

**Delivers:** `slim_course()` turns the raw 4310-byte response into ~450 bytes;
tests assert that `calendar.ics`, `uuid` and any `verifier=` URL never survive.

**Files:** `src/canvas_mcp/filters.py`, `fixtures/courses.json`,
`tests/test_filters.py`

**Branch:** `feat/filters`

**Notes:** fixtures are captured by Leo with curl and anonymised by hand
(user_id, uuids, verifiers) before the agent sees them.

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

**Notes:** this is what makes the repo runnable by someone without a UvA
account, including when Leo's own token has expired.

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

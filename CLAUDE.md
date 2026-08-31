# Conventions for this repo

Read `SCOPE.md` and `ROADMAP.md` before doing anything. Work one roadmap step
at a time using the stepwise-build workflow: brief, implement, report, stop.

## Do not

- commit directly to `main`
- merge your own PR
- add a dependency without asking
- build anything listed under non-goals in `SCOPE.md` (section 7)
- expand a step beyond what the brief described
- read, print or copy the value of `.env`, or of any file holding a real
  credential

The real `CANVAS_TOKEN` lives in `../.env`, outside this repository, so that a
mistake in `.gitignore` cannot leak it. Code reads it from the process
environment; it is never a parameter and never printed.

**One exception, agreed with Leo on 2026-08-30.** The agent may load `.env`
into a subprocess environment (`set -a; . ../.env; set +a`) in order to run
`tools/make_fixture.py`, the only command that needs live credentials. It may
not open the file, echo the value, or pass it to anything else. The capture
prints field names and counts, never values.

## Git

- branches: `feat/`, `fix/`, `docs/`, `chore/`, `test/`, `refactor/`
- Conventional Commits, one logical change per commit
- every PR closes an issue and states what, why, how tested, what was left out
- squash merge

## Code

- Python 3.11+ (developed on 3.13), src layout, package `canvas_mcp`
- `ruff check` and `ruff format` — both enforced in CI
- `pytest`; every behavioural change comes with a test
- filter layer output is asserted field by field: a test per credential-bearing
  field listed in `SCOPE.md` section 5

## Owned by the human — do not write these

- the *design* of `src/canvas_mcp/scopes.py` — the deny-by-default registry
  (roadmap step 4). Settled by Leo on 2026-08-30, decision by decision, with
  the alternatives and reasons recorded in `ROADMAP.md`. Writing the code was
  delegated afterwards, on the grounds that the reasoning was the learning
  goal. Changing any of those decisions is Leo's call, not a refactor.
- tool descriptions and the tuning pass on them (roadmap step 13)
- deciding *when* a live capture runs. The capture itself is automated in
  `tools/make_fixture.py`, which fetches, converts and checks in one process;
  the raw response never reaches disk and never reaches the agent's context
- the claims and argumentation in `README.md` (roadmap step 12) — structure may
  be drafted, conclusions may not
- `.env` and anything containing a real token

You may read these, review them, and write tests against them.

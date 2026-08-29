# Conventions for this repo

Read `SCOPE.md` and `ROADMAP.md` before doing anything. Work one roadmap step
at a time using the stepwise-build workflow: brief, implement, report, stop.

## Do not

- commit directly to `main`
- merge your own PR
- add a dependency without asking
- build anything listed under non-goals in `SCOPE.md` (section 7)
- expand a step beyond what the brief described
- touch `.env` or any file containing a real credential

The real `CANVAS_TOKEN` lives in `../.env`, outside this repository, so that a
mistake in `.gitignore` cannot leak it. Read it from the environment; never
accept a token as a tool parameter.

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

- `src/canvas_mcp/scopes.py` — the deny-by-default registry (roadmap step 4).
  This is the learning goal of the project.
- tool descriptions and the tuning pass on them (roadmap step 13)
- capturing and anonymising fixtures from the live API (roadmap step 3)
- the claims and argumentation in `README.md` (roadmap step 12) — structure may
  be drafted, conclusions may not
- `.env` and anything containing a real token

You may read these, review them, and write tests against them.

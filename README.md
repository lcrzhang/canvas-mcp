# canvas-mcp

A read-only MCP server that gives a language model a narrow view of one
student's Canvas LMS account.

A Canvas personal access token is unscoped: it carries every permission the
person who created it has. Canvas' own scope system only works for OAuth2
developer keys, which an institution has to issue. So for anyone holding a
personal token, **this server is the only place where less than everything can
be enforced**. That is what the project is about, not a detail of it.

```
$ canvas-mcp                                    6 tools
$ canvas-mcp --scopes courses:read,grades:read  2 tools
```

Same token, same code, same request path. What differs is one flag.

## What it does not do

Stated first, because the boundaries are the design.

- **No write tools.** Nothing submits, comments, edits or deletes. There is no
  code path that sends anything but a `GET`.
- **No access to anyone else.** Every tool answers about the person whose token
  the server holds.
- **No file downloads.** Text comes back; files do not.
- **No caching, no OCR, no web UI, no multi-user.** One student, one token,
  locally.
- **No questions across all courses at once.** Every course-scoped tool takes
  one `course_id`, which keeps a single question to a single request.

## Try it without a Canvas account

Demo mode serves committed fixtures instead of the network. No token, no
requests.

```bash
pip install -e .
canvas-mcp --demo
```

In an MCP client — Claude Desktop, for example:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "/path/to/canvas-mcp/.venv/bin/canvas-mcp",
      "args": ["--demo"]
    }
  }
}
```

Then ask *"which courses am I taking?"* and you will get invented ones. Every
value in those fixtures is synthetic; only their shape is real.

For an actual Canvas account, drop `--demo` and supply a token:

```json
{
  "mcpServers": {
    "canvas": {
      "command": "/path/to/canvas-mcp/.venv/bin/canvas-mcp",
      "env": { "CANVAS_TOKEN": "..." }
    }
  }
}
```

**A client keeps the server process alive.** After pulling a new version,
restart the client — otherwise the old code keeps answering, which looks
exactly like a feature that does not work. The server prints its version to
stderr on startup, so the client's log says which code is running, and
`canvas-mcp --version` says what is installed.

The token is read from the environment and is never a tool argument, never
logged, and never printed. Personal access tokens expire after at most 90 days;
a rejected one produces an error that says so and where to make a new one.

## The tools

| Tool | Scope | Default | Answers |
|---|---|---|---|
| `list_courses` | `courses:read` | on | Which courses am I taking? |
| `list_assignments` | `assignments:read` | on | What is due, and did I hand it in? |
| `get_assignment` | `assignments:read` | on | What does this assignment ask for? |
| `list_announcements` | `announcements:read` | on | Has anything been posted? |
| `list_materials` | `materials:read` | on | Which slides belong to week 1? |
| `read_file` | `files:content` | on | What is on slides 10-15? |
| `list_grades` | `grades:read` | **off** | What did I score, per assignment? |

`--scopes` takes a comma-separated list. Omit it and you get the five scopes
above; `grades:read` requires asking for it by name. The list replaces the
default rather than adding to it, so name every scope you want.

A tool outside the enabled scopes is **not registered at all**, rather than
registered and refusing. A model cannot see it and so cannot try. The failure
modes decide it: forgetting to register a tool is an annoyance someone notices
in a minute, while forgetting a permission check inside one is a leak nobody
notices at all.

Every rule lives in one table in `src/canvas_mcp/scopes.py`, and the registry
refuses to start if a tool has no entry there.

## What Canvas actually allows

Established by testing a student token against canvas.uva.nl, not by reading
documentation.

| Endpoint | Result | Date |
|---|---|---|
| `GET /users/self` | 200 | 2026-08-29 |
| `GET /courses?enrollment_state=active` | 200 | 2026-08-29 |
| `GET /courses/:id/modules?include[]=items` | 200 | 2026-08-29 |
| `GET /courses/:id/files` | **403** | 2026-08-29 |
| `GET /courses/:id/files/:file_id` | 200 | 2026-08-29 |
| `GET /users/self/enrollments` | 200, **no score fields** | 2026-08-31 |
| `GET /courses?include[]=total_scores` | 200, **no score fields** | 2026-08-31 |
| `GET /courses/:id/students/submissions?student_ids[]=self` | 200, scores present | 2026-08-31 |
| `GET /courses/:id/files/:id` → the file's `url` | **302** to a signed location | 2026-09-01 |

Three of these shaped the project:

**The course file index is closed to students.** Individual file objects are
reachable, the list of them is not. So the module tree is the only route to a
file id, which is why the tool is called `list_materials` and not `list_files`.

**Final grades are not readable at all here.** The `grades` object in an
enrolment carries only a URL; `current_score` and `final_grade` are absent
rather than null, and `include[]=total_scores` adds nothing. The courses have
`hide_final_grades` set. So the demonstration this project was built around —
*the token may read grades, this server may not* — is **false as stated for
course grades**: Canvas blocks them before this server gets the chance.

**Per-assignment scores are readable.** Hidden final grades do not hide
individual submissions. That is what `list_grades` returns, and it is where the
demonstration actually lives: the token may read those scores, and the server
will not unless started with `grades:read`.

**An active enrolment is not a running term.** `enrollment_state=active` keeps
courses from terms that ended years ago. `list_courses` filters on the term's
end date by default; pass `current_only=false` for the rest.

**A file's `url` is a redirect.** Canvas answers it with a 302 to a signed
location that needs no credential — so the download has to follow redirects,
and the token must not follow with it. It does not: the header is dropped on a
cross-host redirect, and a test says so.

## What the filters remove

Every filter is an allowlist: the output is built from named fields rather than
by removing dangerous ones. A denylist has to be complete to be correct, and
these responses carried fields nobody had predicted — LTI plumbing, moderation
settings, JWT-bearing preview URLs, unauthenticated download links.

Measured on the committed fixtures, which are the real responses with their
values replaced:

| Endpoint | Items | Fields | Raw | Returned | |
|---|---|---|---|---|---|
| `assignments` | 12 | 72 | 64,884 B | 1,329 B | 48.8× |
| `submissions` | 12 | 33 | 64,885 B | 1,357 B | 47.8× |
| `courses` | 6 | 32 | 7,278 B | 601 B | 12.1× |
| `announcements` | 104 | 53 | 201,718 B | 34,184 B | 5.9× |
| `modules` | 3 | 13 | 5,043 B | 1,167 B | 4.3× |

The low numbers are the honest ones. For announcements and modules the payload
*is* the content, so there is little to remove. Reduction is a side effect; the
point is which fields are named.

Named out, with a test each: calendar feed URLs that need no authentication,
`verifier=` download links, `canvadoc_session_url` (a JWT with a user id in
it), `secure_params`, internal account and SIS identifiers, an announcement
author's name, pronouns and avatar, and a student's own submitted work.

## Reading a file

`read_file` takes the id `list_materials` returns and reads the text of a PDF,
one passage at a time: `page_range` is written the way it is printed — `"12"`
or `"10-15"`, counting from 1.

**A lecture deck has far more pages than slides.** LaTeX writes one page per
build-up step, so a 30-slide lecture is often 90 pages: one real deck read
here had 94 pages, and a 20-page range in it held 4 slides. Consecutive pages
that are frames of the same slide are collapsed into one entry, labelled with
the pages it came from, and the reply says how many slides the range held.
Sixty pages may be read at once; twenty slides come back.

Two pages count as one slide when they open with the same text and one's words
are contained in the other's — in either direction, because `\only` makes
content disappear as well as appear, and the fullest frame is kept rather than
the last. Deliberately not based on the slide number some beamer themes print
in the footer: a regex against arbitrary LaTeX that misfires would merge
unrelated slides, silently. A page with no text is never folded into its
neighbour, because it is a page that could not be read rather than a repeat.

Only PDFs, and only ones with a text layer. A scan comes back as a refusal
saying it is probably an image and that this server does no OCR, rather than as
blank pages — silence would read as "that page is empty" about a page full of
handwriting. A file over 25 MB is refused before it is transferred.

Everything that knows what a PDF is lives in two functions, so the backend can
be replaced without touching a tool. It is `pypdf`, and that was measured
rather than assumed.

`pdfplumber` was installed alongside it and read the same lecture deck.
Expectation: better, because it splits words on the distance between glyphs
rather than on whatever the content stream groups — and `pypdf` does lose word
boundaries at formatting changes, turning `while curr_node is not none do` into
`whilecurr_nodeis notnonedo`.

Result: worse, and not repairable. `pdfplumber` reads a page line by line, so
a two-column slide comes out interleaved — `Higher-level, Meetings:` — where
`pypdf` reads one column and then the other. `x_tolerance` changes word
splitting, not order. `layout=True` is visually faithful and pads every line to
the width of the page, which a model pays for by the token. Reading a slide in
the wrong order costs more than losing spaces inside it.

What neither does well is tables. A 3×3 grid of asymptotic bounds comes out as
`O(1)O(n)O(n 2)` above `1∈ ∈ ∈`, with no way to tell which column a symbol
belonged to. PyMuPDF beats both and is AGPL, which this project cannot take
on.

The comparison is kept as a test: a two-column page must come back one column
at a time.

## Untrusted content

Assignment descriptions, announcements and page text are written by third
parties and can contain text aimed at a model. What this server does about it:

1. HTML becomes plain text, with links kept as readable text.
2. The result is capped, with a marker saying how many characters were cut.
3. It is wrapped in delimiters naming it as third-party content — and those
   delimiters are stripped from the body first, so the content cannot close its
   own block and have what follows read as though the server said it.

**This does not solve prompt injection and is not meant to.** An injection
attempt passes through intact; the tests assert that it does, because filtering
it would suggest the problem had been handled. What is actually defended is
simpler: there are no write tools. There is nothing to misuse.

## Fixtures

The fixtures in `fixtures/` are captured responses with **every scalar value
replaced**, not anonymised ones. Structure is preserved exactly — the same
fields, nesting and types — so a filter tested against them meets every field
the live API sends, including the ones nobody anticipated. Values are
regenerated, so nothing real survives because nothing real is copied.

`tools/make_fixture.py` fetches, converts and checks in one process; the raw
response is never written to disk. A guard scans the result before it is
written and again in CI, and refuses anything that still looks live — a real
hostname, an address on a real domain, an unprefixed `verifier=`, a Canvas
token shape, a UUID.

## Development

```bash
pip install -e ".[dev]"
pytest          # no network, no token
ruff check .
ruff format --check .
```

CI runs all three on every pull request. The end-to-end tests start the server
as a real subprocess and speak the MCP protocol to it over stdio, in demo mode,
so they need no credentials.

## Layout

```
src/canvas_mcp/
  client.py      HTTP, pagination, error messages written for a model
  scopes.py      the deny-by-default registry — one table, checked at startup
  filters.py     raw response → the fields a tool returns
  sanitize.py    HTML → bounded, attributed plain text
  fixtures.py    the synthetic converter, its guard, and demo mode
  server.py      MCP entrypoint and tool registration
  tools/         one module per tool
tools/make_fixture.py   capture and convert in one process
```

`SCOPE.md` holds the design and its non-goals; `ROADMAP.md` holds every step
with the decisions taken, the alternatives rejected, and the corrections made
along the way.

## Status

v0.2, on 2026-09-01: seven tools, read-only, 272 tests, confirmed running in
Claude Desktop against canvas.uva.nl. Every claim above was measured or
captured on the date beside it.

Known and written down rather than fixed: a Canvas Page is listed but cannot be
read, since only a File carries an id; extraction quality on multi-column
slides is untested, and `pdfplumber` is the fallback if it disappoints; and
adding one scope means naming the whole default list again.

MIT.

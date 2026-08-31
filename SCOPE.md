# canvas-mcp — Scope & Workflow

Read-only MCP server voor Canvas LMS (canvas.uva.nl).
Eén student, één token, lokaal. Deny-by-default scoping.

---

## 1. Waarom deze server bestaat

Een Canvas personal access token is **ongescoped**: het draagt alle
permissies van de gebruiker die het aanmaakte. Canvas' eigen scope-systeem
werkt alleen bij OAuth2 developer keys, die een instelling moet uitgeven.

Deze server is daarom de enige laag waar least privilege wordt afgedwongen.
Dat is het punt van het project, niet een bijzaak.

---

## 2. Empirisch vastgestelde permissielagen

Getest tegen canvas.uva.nl met een student-token op 2026-08-29:

| Endpoint | Resultaat |
|---|---|
| `GET /users/self` | 200 |
| `GET /courses?enrollment_state=active` | 200 |
| `GET /courses/:id/modules?include[]=items` | 200 |
| `GET /courses/:id/files` | **403 unauthorized** |
| `GET /courses/:id/files/:file_id` | 200 |

Aanvullend getest op 2026-08-31, met hetzelfde token:

| Endpoint | Resultaat |
|---|---|
| `GET /users/self/enrollments?state[]=active` | 200, 7 enrollments |
| `GET /courses?include[]=total_scores` | 200, **geen score-velden** |
| `GET /courses/:id/students/submissions?student_ids[]=self` | 200, **score aanwezig** |

Conclusies die de architectuur bepalen:

- De **file index** vereist `manage_files`-rechten en is dicht voor
  studenten. Individuele file objects zijn wél bereikbaar.
  → Modules zijn de enige ingang naar bestanden.
- Canvas filtert unpublished content zelf al weg op basis van enrollment
  (module `position` 1, 2, 5 — 3 en 4 ontbraken uit de response).
  → `position` is geen index; nooit als zodanig gebruiken.
- Permissies zitten dus op drie lagen: Canvas-instelling, enrollment, en
  deze server. De server is de smalste.

**Cijfers zijn niet leesbaar met dit token.** Het `grades`-object in een
enrollment bevat alleen `html_url`; `current_score`, `current_grade`,
`final_score` en `final_grade` ontbreken — ze zijn niet leeg, ze zitten er niet
in. `include[]=total_scores` op `/courses` voegt evenmin een score toe. De
vakken hebben `hide_final_grades: true`, wat dit verklaart.

Dat is een instellingskeuze van de UvA, geen eigenschap van Canvas, en het kan
per instelling en per vak verschillen. Maar hier geldt: de laag waar cijfers
worden geblokkeerd is Canvas zelf, niet deze server.

**Scores per opdracht zijn wél leesbaar.** Verborgen eindcijfers verbergen de
individuele submissions niet. `GET /courses/:id/students/submissions` met
`student_ids[]=self` geeft `score`, `grade`, `entered_score`,
`points_possible`, `graded_at`, `late`, `missing` en `excused`.

Daar zit dus de demonstratie, en scherper dan het origineel: *"wat had ik voor
opdracht 2"* is zowel nuttig als gevoelig. Het token mag het, deze server niet
tenzij `grades:read` expliciet aanstaat.

Gemeten op 2026-08-31: **12 submissions van één vak zijn 91 363 bytes** over
129 verschillende velden, inclusief `secure_params`, `preview_url`,
`submissions_download_url` en de volledige `description` van elke opdracht. Dat
is de grootste reductie die de filterlaag in dit project maakt, en meteen het
duidelijkste voorbeeld van waarom sectie 5 bestaat.

---

## 3. Tools

### v0.1 — read-only, geen file content

| Tool | Input | Output | Scope |
|---|---|---|---|
| `list_courses` | `term_filter?`, `current_only?` | id, name, code, term-naam | `courses:read` |
| `list_assignments` | `course_id`, `only_upcoming?` | id, name, due_at, points, submitted | `assignments:read` |
| `get_assignment` | `course_id`, `assignment_id` | sanitized plain text, gecapt | `assignments:read` |
| `list_announcements` | `course_id`, `limit?` | titel, datum, plain-text body | `announcements:read` |
| `list_materials` | `course_id`, `module_filter?` | module → sectie → item (naam, type) | `materials:read` |

`current_only` staat standaard aan. Empirisch vastgesteld op 2026-08-31:
`enrollment_state=active` betekent dat je *inschrijving* actief is, niet dat de
*periode* loopt. Canvas gaf zes vakken terug waarvan er drie uit afgesloten
periodes van 2024 en 2025 kwamen. Zonder filter moet een model zelf uitzoeken
wat actueel is — en de faalmodus daarvan is een plausibel verkeerd antwoord,
niet een foutmelding. Een term zonder einddatum telt als lopend; een vak
verbergen op grond van een ontbrekende datum is erger dan er een te veel tonen.

`list_materials` heet bewust niet `list_files`: de bron is de module-tree,
en de output bevat ook pages en assignments, niet alleen bestanden.

### v0.2 — file content

| Tool | Input | Output | Scope |
|---|---|---|---|
| `read_file` | `course_id`, `file_id`, `page_range?` | geëxtraheerde tekst | `files:content` |

### Bestaat, maar staat standaard uit

| Tool | Scope | Waarom uit |
|---|---|---|
| `list_grades` | `grades:read` | Scores per opdracht voor één vak: `course_id` in, opdrachtnaam + score + maximum + status uit. Het token mag het, de server niet tenzij expliciet aangezet. Dit is de demonstratie. |

---

## 4. Wat een gebruiker kan vragen

- "Welke vakken volg ik dit semester?"
- "Wat moet ik deze week inleveren voor Datastructuren?"
- "Waar gaat de week 1 opdracht over?"
- "Welke slides horen bij week 1?"
- "Zijn er nieuwe announcements bij DA?"
- (v0.2) "Wat staat er op slide 10-15 van lec01_intro?"

## Wat expliciet niet kan, by design

- cijfers opvragen zonder `grades:read` expliciet aan te zetten
- iets inleveren, wijzigen of verwijderen — er zijn geen write tools
- vragen over alle vakken tegelijk zonder `course_id` — voorkomt N+1 calls
- bestanden downloaden naar de gebruiker — alleen tekst komt terug

---

## 5. Data hygiene — velden die nooit de output in gaan

Deze bevatten credentials of onnodige PII en worden in de filterlaag
verwijderd, met een test per veld:

| Veld | Reden |
|---|---|
| `calendar.ics` | unauthenticated feed-URL; wie hem heeft leest de agenda |
| `file.url` (met `verifier=`) | unauthenticated download-link |
| `canvadoc_session_url` | JWT met user_id erin |
| `uuid`, `*_account_id`, `sis_*` | interne identifiers, geen nut voor een LLM |
| `storage_quota_mb`, `blueprint`, `template`, `license`, ... | LTI/admin-plumbing |

Gemeten op `/courses` met 4 vakken op 2026-08-29: **4310 bytes ruw → ~450
bytes geslankt** (factor ~9).

Dat is een eenmalige meting tegen de live API, geen testassertie. De fixtures
zijn synthetisch (sectie 8), dus de tests asserten het gedrag — dit veld is
weg, de output is een orde van grootte kleiner — en niet dit exacte getal.

Respecteer daarnaast `locked_for_user` en `hidden_for_user`: staat er
`true`, dan bestaat het item niet voor de tool.

---

## 6. Untrusted content

Assignment-descriptions, announcement-bodies en PDF-tekst zijn door derden
geschreven en kunnen instructies bevatten die op een model gericht zijn.

Mitigatie:

1. HTML → plain text, tags gestript, links behouden als tekst
2. harde cap (~2000 chars) met expliciete `[truncated]` marker
3. content gewrapt in delimiters zodat de grens zichtbaar is

**Eerlijk in de README:** dit lost prompt injection niet op. De echte
verdediging is dat er geen write tools zijn — er is niets om te misbruiken.
Dat is het argument, niet de sanitizer.

---

## 7. Non-goals

Deze staan bovenaan de README, niet onderaan.

- geen write tools (geen submissions, geen comments, geen wijzigingen)
- geen caching layer
- geen OCR — scans zonder tekstlaag worden geweigerd met duidelijke error
- geen multi-user; één token, lokaal
- geen web UI
- geen OAuth2 — alleen Canvas-instances met personal access tokens
- geen file downloads naar schijf voor de gebruiker
- geen v0.1 file content

---

## 8. Fixtures en demo-modus

Twee dingen die vaak door elkaar lopen, met verschillende rechtvaardigingen.

### Fixtures bestaan voor de tests

`tests/test_filters.py` moet kunnen bewijzen dat `calendar.ics`, `uuid` en
verifier-URL's de output niet halen. Dat vereist een realistische input die
niet afhangt van een geldig token of een netwerkverbinding — anders zijn de
tests niet-deterministisch en falen ze zodra het token verloopt.

Deze reden staat op zichzelf. Ook zonder demo-modus zouden de fixtures er zijn.

### Demo-modus bestaat voor de lezer, niet voor de gebruiker

De **gebruiker** van deze server heeft per definitie een Canvas-account; voor
die persoon voegt `--demo` niets toe.

De **lezer** van deze repo is een andere groep. Dit project beweert iets
controleerbaars: de server is smaller dan het token dat hij gebruikt, en
`list_grades` staat uit terwijl het token het wél mag. Wie geen UvA-account
heeft, kan dat niet nagaan en moet de README op zijn woord geloven. Met
`--demo` is het in dertig seconden zelf te zien.

Dat is het argument. "Tokens verlopen na 90 dagen" is dat níét — als je token
verloopt maak je een nieuwe aan.

### Wat demo-modus niet is

- **Geen tweede implementatie.** `CanvasClient` accepteert een `transport`;
  demo-modus is een transport die uit `fixtures/` leest in plaats van van het
  netwerk. Zelfde client, zelfde filters, zelfde tools. Was het een parallel
  codepad geweest, dan zou de onderhoudslast de feature niet waard zijn.
- **Geen bewijs dat de echte API zich zo gedraagt.** Een groene demo zegt dat
  de code klopt tegen een vastgelegde response, niet dat Canvas die response
  vandaag nog zo teruggeeft.
- **Geen volledige dataset.** De fixtures dekken de endpoints die een tool
  nodig heeft, niet elk veld dat Canvas kan sturen.

### Echte vorm, verzonnen waarden

Een fixture wordt één keer afgevangen tegen de live API en behoudt daarna elk
veld dat Canvas stuurt, inclusief de velden die niemand had voorspeld. Alleen
de waarden worden vervangen:

| Wat | Wordt |
|---|---|
| hostname | `canvas.example.edu` |
| `user_id`, course-ids | kleine, zichtbaar nep getallen |
| `uuid`, `verifier=` | `FIXTURE`-prefix, herkenbaar als niet-echt |
| namen, e-mail, vaknamen | verzonnen, maar plausibel genoeg voor een demo |

**Waarom niet met de hand verzinnen.** Een filter die alleen getest wordt tegen
velden die je al kende, bewijst niets over de velden die je vergat. De rauwe
`/courses`-response bevatte LTI- en admin-plumbing die niet was voorzien; dat
is precies waarom sectie 5 bestaat. De vorm moet echt zijn om de filtertest
betekenis te geven.

**Waarom niet gitignoren.** Dan werkt `--demo` niet voor wie de repo cloont, en
dat is de enige reden dat fixture-mode bestaat.

Fixtures zijn hiermee de enige plek waar echte API-data de repo binnen zou
kunnen komen. Ze worden door Leo afgevangen en omgezet; een test bewaakt dat er
niets echts achterblijft (roadmap stap 3b). Een `verifier=`-URL is een
werkende, niet-geauthenticeerde downloadlink — in een publieke repo is dat
permanent, ook na een latere commit die hem weghaalt.

---

## 9. Error handling

Errors zijn instructies voor een LLM, geen statuscodes.

```
401 → "Canvas token rejected. Personal access tokens expire after max 90
       days — generate a new one at canvas.uva.nl → Account → Settings."
403 → "Not authorised for this endpoint. The course file index requires
       teacher permissions; use list_materials instead."
404 → "Course 60059 not found or not visible with this enrollment."
```

Startup-check: valideer het token één keer tegen `/users/self` en fail fast.

---

## 10. Repo-structuur

```
canvas-mcp/
├── src/canvas_mcp/
│   ├── __init__.py
│   ├── server.py        # MCP entrypoint, tool registratie
│   ├── client.py        # HTTP layer, auth, error mapping
│   ├── scopes.py        # deny-by-default registry
│   ├── filters.py       # ruwe API-response → slim dict
│   ├── sanitize.py      # HTML → plain text, caps
│   └── tools/
│       ├── courses.py
│       ├── assignments.py
│       ├── announcements.py
│       └── materials.py
├── fixtures/            # geanonimiseerde JSON voor --demo
├── tests/
├── .env.example         # CANVAS_TOKEN=
├── .gitignore           # .env
├── pyproject.toml
├── README.md
└── SCOPE.md
```

---

## 11. Git workflow

**Branches** — geen directe commits op `main`, ook niet solo.

```
feat/<naam>   nieuwe tool of feature
fix/<naam>    bugfix
docs/<naam>   README, scope
chore/<naam>  CI, deps, config
```

**Commits** — Conventional Commits, één logische verandering per commit.

```
feat(tools): add list_assignments with due_at filtering
fix(client): map 401 to actionable token error
docs(scope): document empirically tested permission layers
test(filters): assert verifier URLs are stripped
chore(ci): run ruff and pytest on PRs
```

**Merges** — squash merge per PR. Trade-off: tussenstappen binnen een branch
verdwijnen uit `main`, maar de log wordt leesbaar als changelog. De volledige
geschiedenis blijft zichtbaar in de PR zelf.

**Issues** — elke unit of work een issue, elke PR sluit er één
(`Closes #7`). PR-beschrijving: wat, waarom, hoe getest.

**CI** — vanaf de eerste PR: `ruff check`, `ruff format --check`, `pytest`.

**Releases** — semver + tag. `v0.1.0` als de vijf tools werken,
`v0.2.0` bij `read_file`.

---

## 12. Milestones

| Milestone | Inhoud |
|---|---|
| `v0.1.0` | client, scopes, filters, 5 read-only tools, fixture mode, CI, README |
| `v0.2.0` | `read_file` met page_range en size caps |
| backlog | `list_grades` documentatie-voorbeeld, term-resolutie via `include[]=term` |

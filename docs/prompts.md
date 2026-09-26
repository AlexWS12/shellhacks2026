# Agent prompts

Run these in order, one prompt per agent session, and commit after each one passes its checks.

## Before you start

Five minutes of setup make every prompt below work without extra explanation.

1. Create an empty Git repo named `tandem` and open it in your coding agent (Claude Code or similar).
2. Export the main tab of this doc as Markdown and save it as `docs/architecture.md` in the repo. Every prompt points the agent there.
3. Put the source files in `data/sources/`: the Dominion PDF, `2025_IRP_Volume_3_PUBLIC_DISCLOSURE.pdf`, and `Projects_Overlaps.xlsx`. Put the published artifact's HTML in `docs/reference/tandem-real-data.html` as the UI reference.
4. Install locally: Python 3.12, `uv`, Node 20+, `pnpm`, Docker, and poppler (`pdftotext`).
5. Get a Gemini API key; you'll need it from prompt 13 on. It goes in `.env`, never in code.

**How to run each prompt**

- One prompt per session. Start a fresh session for each so the agent re-reads `CLAUDE.md` and the plan.
- Paste the prompt as written. Each one ends with checks the agent must run and a request to stop and report.
- If the checks pass, commit with the prompt number in the message (`P03: runner and event log`). If they fail, stay in the session and paste the failing output.
- Prompts 1–6 are sequential. After prompt 6, the four owners can run prompts in parallel on branches: data and geo (7, 8, 9, 10), pipeline and agents (13, 14), web (12, 15, 17), product and demo (11, 16).

## M0: Scaffold (prompts 1–6)

The goal of M0 is a running skeleton: stub stages emit real events, the API streams them, and the web app draws them. No real data yet.

**Prompt 1: Orient, write no code**

```text
Read docs/architecture.md completely. It is the implementation plan for Tandem.
Do not write any application code in this session.

1. Create CLAUDE.md at the repo root. Copy the "Agent rules" list from the plan verbatim,
   then add a short "Project map" section listing each top-level folder from
   "Repository layout" with one line on what it holds.
2. Reply with: (a) a 5-bullet summary of the architecture in your own words,
   (b) any contradictions or gaps you found in the plan, (c) questions you need answered
   before scaffolding.
Stop after that.
```

**Prompt 2: Monorepo and tooling**

```text
Follow CLAUDE.md and docs/architecture.md. Task: milestone M0, repo scaffold only.

Create the folder layout in "Repository layout" exactly. Put a one-paragraph README.md in
each package, service, and app.
- Python: uv workspace with packages/core (tandem_core), services/runner (tandem_runner),
  services/api (tandem_api). Python 3.12. ruff, mypy --strict, pytest configured at the root.
- Web: pnpm workspace; apps/web as Next.js 15 (App Router, TypeScript strict), vitest.
- Makefile targets: dev, test, lint, types, record (record can be a stub that prints TODO).
- docker-compose.yml with api (port 8000) and web (port 3000) services.
- .env.example with GEMINI_API_KEY= and TANDEM_DB=data/tandem.db. Add .env and data/*.db to .gitignore.
- One trivial passing test per Python package and one vitest test in apps/web.
- GitHub Actions workflow running make lint and make test.

Checks: make lint and make test pass; make dev starts both services. Report the tree
(depth 3) and command output, then stop.
```

**Prompt 3: Domain models and generated types**

```text
Follow CLAUDE.md. Task: the contract in "Domain model and event contract".

- In packages/core/tandem_core/models.py define Provenance, Location, Endpoint, Project,
  Overlap, Check as frozen Pydantic v2 models, exactly as the plan specifies.
- Define events as a discriminated union on `type`: run.started, stage.started,
  stage.completed, record.extracted, endpoint.located, check.raised, overlap.found,
  reference.tested, brief.written, run.completed. Every event has run_id, seq, ts, type, payload.
- scripts/export_schema.py writes one JSON Schema per model and one for the Event union
  into packages/contracts/schema/.
- scripts/gen_types.sh generates TypeScript into packages/contracts/ts/ with
  json-schema-to-typescript. make types runs both.
- Import the generated Event type in apps/web and use it in a type-only test.
- Tests: models are immutable (assignment raises), round-trip JSON, schema export is
  deterministic (run twice, identical files).

Checks: make types, make test, make lint pass. Stop and report.
```

**Prompt 4: Declarative runner and event log**

```text
Follow CLAUDE.md. Task: the imperative shell in services/runner.

- Write pipeline.yaml at the repo root exactly as in "Pipeline spec".
- dag.py: load pipeline.yaml, validate it (unknown inputs, cycles, missing fns are errors),
  topologically sort stages, and run them. Stages declare `fn` as a dotted path.
- For now implement every core fn as a stub in tandem_core that returns an empty or tiny
  hard-coded result of the right model type. No real parsing yet.
- Effects are values: a stage fn may return EffectRequest objects; the runner executes them
  via services/runner/tandem_runner/effects/*, stores results in effect_cache keyed by the
  SHA-256 of the canonical request JSON, and calls the fn again with results. Stub effects only.
- events.py: SQLite tables runs, events(run_id, seq, type, payload_json, ts),
  effect_cache(hash, request_json, response_json). Append-only; seq is gapless per run.
- Honor timeout_s and fallback: "last_recorded" (use the latest successful stage output from
  a previous run) and "template". Emit stage.completed with used_fallback true/false.
- `today` comes from pipeline.yaml run.today and is passed into fns. Never read the clock in core.
- CLI: `python -m tandem_runner run` prints events as JSON lines.

Checks: running the CLI twice produces the same event sequence (ignoring ts and run_id);
a test forces a stage timeout and asserts the fallback event; make test passes. Stop and report.
```

**Prompt 5: API with SSE**

```text
Follow CLAUDE.md. Task: services/api with FastAPI, per "API and frontend".

Endpoints: POST /runs (starts a run in a background task, returns id), GET /runs,
GET /runs/{id}/events as Server-Sent Events with ?from_seq= resume and ?replay=1&speed=N,
GET /runs/{id}/state. Leave export.xlsx and diff returning 501 for now.

Write tandem_core/reduce.py: a pure function reduce(state, event) -> state and
fold(events) -> RunState. /state returns fold(events). Store 3 recorded stub runs in
data/runs/ via make record.

Checks: a test starts a run and reads the SSE stream to run.completed; replay of a stored
run emits identical payloads in the same order; make test passes. Stop and report.
```

**Prompt 6: Web shell driven by events**

```text
Follow CLAUDE.md. Task: apps/web shell. Use docs/reference/tandem-real-data.html as the
visual reference for layout, colors, and fonts. Do not copy its code; rebuild it in React.

- lib/reducer.ts: pure (state, event) => state using the generated Event type. It must
  produce the same JSON as tandem_core.reduce.fold for the fixtures in data/runs/.
  Add a shared test that loads those fixtures in both vitest and pytest.
- lib/selectors.ts: pure filtering and sorting (empty for now).
- Page /: three columns (pipeline panel, map, opportunities) and a header with Run and
  Replay buttons. Run posts /runs and subscribes to SSE; Replay picks the latest recorded run.
- Map: MapLibre with the OpenFreeMap style URL from lib/config.ts, centered on the SC–GA border.
  No data layers yet.
- Pipeline panel shows stage names and states from events, updating live.
- Light and dark themes via CSS variables; keyboard focus visible.

Checks: make dev, click Run, stages tick to done; the reducer parity test passes;
make lint and make test pass. Stop and report with a screenshot if you can take one.
```

## M1: Deterministic parity (prompts 7–12)

The goal of M1 is the artifact's results from real code: 44 plus 208 projects, the sponsor's 6 overlaps reproduced exactly, 19 overlaps under default filters, and the known data issues found. The numbers in these prompts come from the artifact run, so the agent has targets to hit.

**Prompt 7: Dominion parser**

```text
Follow CLAUDE.md. Task: tandem_core/parse_desc.py, a pure function
parse(text: str, file: str) -> tuple[list[Project], list[Check]].
The runner's read_pdf_text effect supplies text from `pdftotext -layout`; implement that
effect now (subprocess, cached by file hash).

Facts about the file (verified):
- 44 projects, one per page; pages split on form feed (\f).
- Labels on their own lines: "5 Year Budget" (name follows until "Project ID"),
  "Project ID", "Project Description", "Project Need", "Project Status",
  "Planned In-Service Date", "Estimated Project Cost".
- The cost row follows the line starting "Previous": 7 dollar values
  (Previous, 2024–2028, Total).
- Dates mix formats: 12/31/23, 12/31/2024, 06/01/24. Normalize to date.
- Project 34 (Dawson) has two dates "(phase 1) and ... (phase 2)": use the last, emit a Check.
- Project 22 (Riverport Tap) has "$19,00,181": do not guess; set that year to None, emit
  an error Check, keep the total.
- IDs look like "06367 D - G", "0139 M,N", "1060A, I, L". Project.id = "DESC-" + ID with
  whitespace removed. Keep the raw ID in provenance.locator.
- build_start = Jan 1 of the first year 2024–2028 with spending, or None if Previous > 0.
- length_mi from "N miles" in the name or description when present.

Tests: 44 projects; spot-check projects 1, 22, 23, 34, 44 field by field against the PDF;
parse is deterministic. Stop and report the table of id, name, in_service, total.
```

**Prompt 8: Georgia parser**

```text
Follow CLAUDE.md. Task: tandem_core/parse_georgia.py, pure, same signature as parse_desc.

Facts about the IRP (verified): 668 pages; the "2024 GA ITS Ten-Year Plan (2025-2034)"
section has a summary table plus one page per project.
- Summary rows match: zone (3 digits), year, TEAMS number (4–6 digits), project name
  (may wrap onto following lines), need date, sponsor. All cost columns read "REDACTED".
- Each project page has the title line, "Teams # N", "Need Date MM/DD/YYYY Start Date
  MM/DD/YYYY", and a "Description" block ending before "Supporting Statement".
- Join rows to pages by TEAMS number. Expect 208 of each and zero unmatched on either side.
- Sponsor counts: GPC 122, GTC 54, SAV 16, MEAG 14, DU 2.
- Use the page title as the name when the table name is truncated.
- Project.id = "GA-" + TEAMS. utility = "GPC" for all rows; sponsor keeps the real value.
- cost_total = None. Emit one info Check for redacted costs and one for the CEII banner.
- Never read or store anything from a REDACTED field.

Tests: counts above; TEAMS 20277 is "SAV: MCINTOSH - PURRYSBURG 230KV REACTORS",
need 2026-06-01, start 2024-01-01, page 227. Stop and report.
```

**Prompt 9: Reference loader, endpoints, and first-pass locate**

```text
Follow CLAUDE.md. Tasks in tandem_core: parse_reference.py, endpoints.py, locate.py.

parse_reference: read both sheets of Projects_Overlaps.xlsx (effect: read_xlsx).
in_service_date mixes text and real Excel dates (DESC_5, GPC_4): normalize and emit a
warn Check. McIntosh appears with two coordinates about 0.41 mi apart: emit a warn Check.
Map each sponsor row to a parsed project by normalized name (treat en dash as hyphen);
DESC_1 maps to DESC-6809E. Expected: all 10 map.

endpoints.split(name) -> list[str], at most 2: strip sponsor prefixes (SAV:, GTC:, MEAG:,
DU:, CC -, GRID -), text after ":", parentheses, voltages, "#n", and words like Sub,
Substation, Tap, Line, Rebuild, Construct, Reconductor, Upgrade. Split on hyphen or en dash.

locate.resolve: priority (1) sponsor coordinates at project level for the 10 reference
projects, using each row's own coordinates; (2) sponsor endpoint coordinates by normalized
name; (3) GeoNames towns (population over 1,000; data/reference/geonames_sc_ga.csv from
scripts/fetch_gazetteer.py) with an exact name match in the project's own state only,
after removing generic words (Primary, Dam, Energy, Reservoir, County, trailing numbers).
No first-word or partial matches. Confidence: verified, town, or unlocated with a reason.
Center = mean of located endpoints.

Tests: the 10 reference projects are verified with the sponsor's centers; "Union Pier"
does not match Union, SC. Report counts by confidence (expect about 14 verified,
85 town or partial, 153 unlocated). Stop.
```

**Prompt 10: Overlap engine and golden test**

```text
Follow CLAUDE.md. Tasks: tandem_core/geometry.py, overlap.py (find, test_reference), rank.py.

- haversine_mi with Earth radius 3958.8 mi. distance_mi = center to center, rounded to 2.
- closest_mi: nearest points between the two projects' geometries (point or line) using
  shapely in a local metric projection; informational only.
- gap_days = abs(in_service_a - in_service_b).
- windows_overlap when both have build_start and the intervals intersect.
- find(projects, config): DESC x Georgia pairs, sponsors filtered by config, distance < 25.
- test_reference: re-derive the sponsor's 6 overlaps using our parsed dates.
- rank: by distance, then gap.

Remove expected-fail from the golden test. It must pass: 4.09/3074, 5.65/152, 7.55/517,
8.01/3074, 14.34/365, 14.81/730. Also assert 19 overlaps with default config.
Add Hypothesis property tests for distance. Wire the stages into pipeline.yaml for real.
Stop and report the ranked list.
```

**Prompt 11: Validation rules**

```text
Follow CLAUDE.md. Task: tandem_core/validate/, one module per rule V-01 to V-14 from
"Validation rules", registered in __init__.py; run_all returns Checks in a stable order.

Rules raise checks and never change data. For each rule write two tests: its real example
from the plan and a clean counter-example. The full run must surface at least the 17
issues the artifact found (malformed amount, cost-sum gaps, spend after in-service, phased
dates, mixed date types, duplicate McIntosh coordinates, redacted costs, CEII banner,
sponsor scope, past in-service dates, unlocated projects). Stop and report all checks.
```

**Prompt 12: Wire the UI to real data**

```text
Follow CLAUDE.md. Task: apps/web shows a real run.

- deck.gl layers over MapLibre: project pins (Dominion teal, Georgia indigo; solid when
  verified, hollow when town-level), lines when both endpoints are located, dashed
  overlap links with a mile label, a 25-mile ring for the selected pair.
- Pins appear as endpoint.located events arrive; links as overlap.found arrives.
- Pipeline panel: sources with progress, agents with state and counts, reference check
  table (6/6), data checks list, unlocated list, activity feed.
- Right panel: stats (read, on map, under 25 mi), ranked list sortable by distance and by
  gap, badges for confidence and "In sponsor sample".
- Selectors recompute overlaps client-side with the same haversine and shared test
  vectors from the Python tests.

Checks: a full run in the browser matches the artifact's top 5 pairs; keyboard can reach
every list item; vitest and Playwright smoke test pass. Stop and report with a screenshot.
```

## M2 and M3: Real agents and product (prompts 13–18)

M2 replaces the gazetteer and templates with real agents; M3 finishes the features judges will click. Prompt 18 is the freeze.

**Prompt 13: Overpass and Nominatim geocoding**

```text
Follow CLAUDE.md. Task: real geocoding effects and matching, per "Pipeline spec".

- effects/overpass.py: one query per operator over a bounding box covering SC and GA:
  nwr["power"="substation"]["operator"~"<operator>",i](30.3,-85.7,35.3,-78.4); out center tags;
  operators: Dominion Energy South Carolina (also SCE&G), Georgia Power, Georgia Transmission,
  MEAG. Cache by request hash. Respect rate limits with backoff. Save responses to
  data/fixtures/ so tests and demos run offline.
- locate.resolve (pure) gains a new priority after sponsor coordinates: match endpoint
  names against Overpass feature names (normalized; fuzzy score with a threshold; same
  operator family and state). One strong match -> confidence high. Several -> an
  llm_disambiguate EffectRequest with the project description and candidate tags.
- effects/nominatim.py as the next fallback for unmatched endpoints (1 request/second,
  descriptive User-Agent), then the town gazetteer.
- effects/gemini.py: structured JSON output through LiteLLM; the prompt includes only the
  project's public fields and candidates; response schema {candidate_id | null, reason}.
- V-13 must catch any match outside the project's state or zone.

Checks: offline run from fixtures is deterministic; the golden test still passes; report
new counts by confidence and the 10 riskiest matches for human review. Stop.
```

**Prompt 14: Brief writer agent**

```text
Follow CLAUDE.md. Task: the briefs stage for the top 5 opportunities.

tandem_core/briefs.py (pure) builds the prompt from the Overlap and both Projects' public
fields only, and validates the response: every number or date in the output must appear
in the input fields, else reject. Output schema: {dominion_position, georgia_position,
mediator_summary, shareable: [crews|equipment|staging|right_of_way|outage_planning|
survey_data], cited_fields: [...]}. Gemini via the gemini effect, cached.
Fallback "template": deterministic text from the same fields, marked as template in the event.

Checks: a test with a fixture response passes validation; a response with an invented
dollar figure is rejected and falls back; brief.written events appear. Stop.
```

**Prompt 15: Opportunity detail and filters**

```text
Follow CLAUDE.md. Task: apps/web detail view and filters.

- Clicking a list item or overlap link opens the detail panel and flies the map to the pair:
  distance (center to center, plus closest point in smaller text), gap in days, confidence,
  build-window chart (Dominion from first spend year, Georgia from start date; overlap shaded),
  the brief, filing descriptions, costs (Dominion public, Georgia "redacted in the filing"),
  and provenance per endpoint (file, page, method, evidence).
- Header filters: all Georgia sponsors (default GPC + SAV), include town-level locations,
  hide finished projects (uses run.today). Filters never start a run.
- Clicking a pin shows that project and its pairs under 25 mi.
- Reduced-motion disables camera flights.

Checks: toggling each filter changes counts consistently in list, map, and stats;
Playwright covers open, filter, and back. Stop.
```

**Prompt 16: Cost model and export**

```text
Follow CLAUDE.md. Tasks: tandem_core/cost.py and GET /runs/{id}/export.xlsx.

cost.py: pure. For pairs with overlapping build windows, estimate savings from one avoided
mobilization and shared staging as a range over Dominion's public cost. Every assumption is
a named constant with a source string and URL in config; leave the URL empty and mark
"needs source" rather than inventing one. No estimate when windows don't overlap.

Export with openpyxl, Arial: sheets projects and overlaps in the sponsor's exact column
order (see Projects_Overlaps.xlsx), then extra columns (sponsor, location_confidence,
build_start, estimated_cost, status, source); plus data_checks, reference_test, notes.

Checks: open the file with pandas; sponsor columns match the sponsor file's headers in
order; 19 overlap rows under default config. Stop.
```

**Prompt 17: Replay and diff**

```text
Follow CLAUDE.md. Tasks: replay control and the diff view.

- Replay: header control to pick a recorded run and speed (1x, 4x, 10x). Uses
  /runs/{id}/events?replay=1. Works with the API's network egress disabled.
- make record saves the current full run to data/runs/ with its effect cache.
- GET /runs/{a}/diff/{b}: pure diff in tandem_core over folded states: projects added,
  removed, changed (fields listed); overlaps added, removed, moved (distance or gap changed).
- /runs/[id]/diff/[other]: map colors by change type, list grouped by change.
- Test: copy the Dominion source, change one in-service date in the parsed fixture, run,
  and assert the diff shows exactly that change.

Checks: replay with networking off completes; diff test passes. Stop.
```

**Prompt 18: Freeze and demo readiness**

```text
Follow CLAUDE.md. No new features. Task: demo readiness.

1. Run make lint, make test, Playwright, and an accessibility scan (axe) on / and a detail
   view. Fix only failures.
2. Record two fallback runs (full, and full with network off) into data/runs/.
3. Time each stage cold and warm; report against the NFR targets.
4. Write docs/demo.md: the three-act script (documents become a map, overlaps and
   provenance, one opportunity end to end), what to click, and the fallback if anything
   stalls.
5. Update README.md with setup in under 10 commands.
Report results and anything that misses a target. Stop.
```

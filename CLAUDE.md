# Tandem

Implementation plan: `docs/architecture.md`. Read it before starting work.

## Agent rules

- DO NOT put I/O, network calls, randomness, or `date.today()` in `packages/core`. Pass everything in.
- DO NOT mutate records. Return new frozen models.
- DO NOT add a pipeline stage by editing the runner. Add it to `pipeline.yaml` and implement a pure function.
- DO NOT use an LLM for distance, dates, ranking, or cost math.
- DO NOT use or reconstruct REDACTED or CEII-marked values. Public fields only.
- DO NOT edit generated types in `packages/contracts/ts`. Change the Pydantic model and regenerate.
- DO NOT merge if the golden test is below 6/6.
- ALWAYS attach Provenance to every derived value.
- ALWAYS emit an event for a state change; UI state comes only from `reducer.ts`.
- ALWAYS cache effect results by request hash and support running with the network off.
- DO NOT add Kafka, Redis, Celery, LangChain, a vector database, or extra services.
- DO NOT hardcode utility ids, comparison pairs, the LLM model id, or the basemap style URL. They come from `pipeline.yaml`, env, or `apps/web/lib/config.ts`.
- DO NOT rename or move files in `data/sources/`. Quote paths that contain spaces.
- DO NOT use an LLM to extract fields from filings (ADR-007). An unparseable page raises an error Check and the record is skipped.

## Project map

This repo's root is the plan's `tandem/` root.

- `.github/`: GitHub Actions CI workflow (lint, type checks, tests per package).
- `data/`: source filings and sponsor xlsx committed with original filenames (`sources/`), the GeoNames SC/GA gazetteer with attribution (`reference/`), cached effect results for offline tests (`fixtures/`), and recorded event logs for demo fallback (`runs/`).
- `packages/`: `core/` is the pure functional core (models, parsers, geometry, validation, overlap, rank, cost, reducer); `contracts/` holds JSON Schema exported from core and the generated TypeScript types.
- `services/`: `runner/` is the imperative shell (reads `pipeline.yaml`, runs the DAG, executes and caches effects, appends events); `api/` is FastAPI serving runs, SSE event streams, and exports.
- `apps/`: `web/` is the Next.js UI (live run, run view, diff) whose state is a pure reduction of events.
- `scripts/`: schema export, TypeScript generation, run recording, and gazetteer fetch.
- `docs/`: `architecture.md`, the plan and its decisions, kept current; `reference/` holds the locations guide, challenge brief, and artifact HTML.

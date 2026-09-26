# tandem_api

The FastAPI service on port 8000. It starts runs, lists recent runs, streams a run's events over Server-Sent Events (live or replayed), serves the folded RunState snapshot, exports the sponsor-schema workbook, and diffs two runs. In the scaffold it exposes only `GET /health`. Start it alone with `uv run uvicorn tandem_api.main:app --reload --port 8000`, or with the web app via `make dev`.

"""Tandem HTTP API: runs, their SSE event streams, and folded state."""

import logging
import sqlite3
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.sse import EventSourceResponse, format_sse_event
from pydantic import BaseModel, ConfigDict

from tandem_api.settings import Settings
from tandem_core.models import Event, RunCompleted, RunCompletedPayload, RunState
from tandem_core.reduce import fold
from tandem_runner.cache import EffectCache
from tandem_runner.config import PipelineConfig, load_config
from tandem_runner.dag import PipelineError, Runner, plan
from tandem_runner.events import EVENT, EventLog, open_db

log = logging.getLogger("tandem_api")


class RunRequest(BaseModel):
    """Optional overrides for one run. Source paths are relative to data/sources/."""

    model_config = ConfigDict(extra="forbid")

    sources: dict[str, str] = {}
    sponsors: list[str] | None = None
    today: date | None = None


class RunCreated(BaseModel):
    run_id: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    today: str
    started_at: str | None
    totals: dict[str, int]
    recorded: bool  # loaded from data/runs/ (the demo fallback), not run by this server


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    pending: set[str] = set()  # accepted by POST /runs, not yet in the database
    recorded: set[str] = set()  # run ids found in settings.runs_dir
    pending_lock = threading.Lock()

    @contextmanager
    def connect() -> Iterator[EventLog]:
        db = open_db(settings.db_path)
        try:
            yield EventLog(db)
        finally:
            db.close()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with connect() as events:
            for path in sorted(settings.runs_dir.glob("*.jsonl")):
                run = [EVENT.validate_json(line) for line in _lines(path)]
                if not run:
                    continue
                recorded.add(run[0].run_id)
                if events.import_run(run):
                    log.info("imported recorded run %s from %s", run[0].run_id, path.name)
        yield

    app = FastAPI(title="Tandem API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", status_code=202)
    def start_run(request: RunRequest | None = None) -> RunCreated:
        config = _apply_overrides(settings, load_config(settings.config_path), request)
        try:
            plan(config)
        except PipelineError as exc:
            raise HTTPException(422, str(exc)) from exc
        run_id = uuid.uuid4().hex
        with pending_lock:
            pending.add(run_id)
        thread = threading.Thread(
            target=_run_in_background,
            args=(settings, config, run_id, pending, pending_lock),
            name=f"run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return RunCreated(run_id=run_id)

    @app.get("/runs")
    def list_runs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[RunSummary]:
        with connect() as events:
            return [
                RunSummary(
                    run_id=r.run_id,
                    status=r.status,
                    today=r.today,
                    started_at=r.started_at,
                    totals=r.totals,
                    recorded=r.run_id in recorded,
                )
                for r in events.list_runs(limit)
            ]

    @app.get("/runs/{run_id}/state")
    def run_state(run_id: str) -> RunState:
        with connect() as events:
            if events.run_info(run_id) is None:
                if run_id in pending:
                    return fold([]).model_copy(update={"run_id": run_id})
                raise HTTPException(404, f"run {run_id} not found")
            return fold(events.events(run_id))

    @app.get("/runs/{run_id}/events", responses={200: {"content": {"text/event-stream": {}}}})
    async def run_events(
        run_id: str,
        request: Request,
        from_seq: Annotated[int, Query(ge=0)] = 0,
        replay: bool = False,
        speed: Annotated[float, Query(ge=1, le=10)] = 1.0,
        last_event_id: Annotated[str | None, Header()] = None,
    ) -> Response:
        """Stream a run's events as SSE: `id` is the seq, `data` the Event JSON.

        Live (default): sends stored events from `from_seq`, then new ones as the run
        appends them, and closes after run.completed. A browser EventSource that
        reconnects resumes from its Last-Event-ID.

        Replay (`replay=1`): re-emits a finished run with its original spacing divided
        by `speed` (1 to 10), each gap capped at 2 s.
        """
        if last_event_id is not None and last_event_id.isdigit():
            from_seq = max(from_seq, int(last_event_id) + 1)
        with connect() as events:
            info = events.run_info(run_id)
            if info is None and run_id not in pending:
                raise HTTPException(404, f"run {run_id} not found")
            finished = info is not None and info.status != "running"
            if replay:
                if not finished:
                    raise HTTPException(409, "only a finished run can be replayed")
                return EventSourceResponse(
                    _replay(settings, events.events(run_id, from_seq=from_seq), speed)
                )
            if finished and not events.events(run_id, from_seq=from_seq):
                return Response(status_code=204)  # nothing left; stops EventSource retries
        return EventSourceResponse(_live(settings, request, run_id, from_seq))

    @app.get("/runs/{run_id}/export.xlsx")
    def export_xlsx(run_id: str) -> Response:
        raise HTTPException(501, "export arrives in M3")

    @app.get("/runs/{a}/diff/{b}")
    def diff_runs(a: str, b: str) -> Response:
        raise HTTPException(501, "diff arrives in M3")

    return app


# --- Background runs --------------------------------------------------------------


def _run_in_background(
    settings: Settings,
    config: PipelineConfig,
    run_id: str,
    pending: set[str],
    pending_lock: threading.Lock,
) -> None:
    db = open_db(settings.db_path)
    events = EventLog(db)
    try:
        runner = Runner(
            config,
            events,
            EffectCache(db),
            root=settings.root,
            llm_model=settings.llm_model_override or config.llm.model,
        )
        runner.run(run_id)
    except Exception:
        log.exception("run %s crashed", run_id)
        _close_crashed_run(events, run_id)
    finally:
        with pending_lock:
            pending.discard(run_id)
        db.close()


def _close_crashed_run(events: EventLog, run_id: str) -> None:
    """Make sure a crashed run still ends with run.completed so streams terminate."""
    info = events.run_info(run_id)
    if info is None or info.status != "running":
        return
    try:
        events.append(
            run_id,
            RunCompleted,
            RunCompletedPayload(status="failed", totals={}, output_hashes={}),
        )
    except sqlite3.Error, KeyError:
        log.exception("could not close run %s", run_id)
    events.finish_run(run_id, "failed")


def _apply_overrides(
    settings: Settings, config: PipelineConfig, request: RunRequest | None
) -> PipelineConfig:
    if request is None:
        return config
    sources = dict(config.sources)
    base = settings.sources_dir.resolve()
    for sid, relative in request.sources.items():
        if sid not in sources:
            raise HTTPException(422, f"unknown source {sid!r}")
        path = (base / relative).resolve()
        if not path.is_relative_to(base):
            raise HTTPException(422, f"source {sid!r}: path must stay inside data/sources/")
        if not path.is_file():
            raise HTTPException(422, f"source {sid!r}: {relative!r} not found in data/sources/")
        rel_to_root = path.relative_to(settings.root.resolve()).as_posix()
        sources[sid] = sources[sid].model_copy(update={"path": rel_to_root})
    run_updates: dict[str, Any] = {}
    if request.sponsors is not None:
        run_updates["georgia_sponsors"] = tuple(request.sponsors)
    if request.today is not None:
        run_updates["today"] = request.today
    return config.model_copy(
        update={"sources": sources, "run": config.run.model_copy(update=run_updates)}
    )


# --- Streams ----------------------------------------------------------------------


def _sse(event: Event) -> bytes:
    return format_sse_event(data_str=EVENT.dump_json(event).decode(), id=str(event.seq))


async def _live(
    settings: Settings, request: Request, run_id: str, from_seq: int
) -> AsyncIterator[bytes]:
    next_seq, idle = from_seq, 0.0
    db = open_db(settings.db_path)
    try:
        events = EventLog(db)
        while not await request.is_disconnected():
            batch = events.events(run_id, from_seq=next_seq)
            for event in batch:
                yield _sse(event)
                next_seq = event.seq + 1
                if event.type == "run.completed":
                    return
            if batch:
                idle = 0.0
            elif idle >= settings.heartbeat_s:
                yield format_sse_event(comment="ping")
                idle = 0.0
            await settings.sleep(settings.poll_interval_s)
            idle += settings.poll_interval_s
    finally:
        db.close()


async def _replay(settings: Settings, events: list[Event], speed: float) -> AsyncIterator[bytes]:
    previous = None
    for event in events:
        if previous is not None:
            gap = (event.ts - previous).total_seconds() / speed
            await settings.sleep(min(max(gap, 0.0), settings.replay_max_gap_s))
        previous = event.ts
        yield _sse(event)


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


app = create_app()

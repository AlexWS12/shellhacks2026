"""The event log: append-only SQLite storage plus in-process publish.

Tables: runs, events (append-only, gapless seq per run, enforced by triggers),
effect_cache (see cache.py), and stage_outputs (each stage's output per run, the
source for the `last_recorded` fallback).
"""

import importlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter

from tandem_core.models import Event, EventBase
from tandem_core.stage import StageOutput

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    config_hash TEXT NOT NULL,
    today       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed'))
);

CREATE TABLE IF NOT EXISTS events (
    run_id       TEXT    NOT NULL REFERENCES runs (run_id),
    seq          INTEGER NOT NULL,
    type         TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    ts           TEXT    NOT NULL,
    fixture      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, seq)
);

CREATE TRIGGER IF NOT EXISTS events_seq_gapless BEFORE INSERT ON events
WHEN NEW.seq != (SELECT COUNT(*) FROM events WHERE run_id = NEW.run_id)
BEGIN SELECT RAISE(ABORT, 'events.seq must be gapless per run'); END;

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;

CREATE TABLE IF NOT EXISTS effect_cache (
    hash          TEXT PRIMARY KEY,
    request_json  TEXT NOT NULL,
    response_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_outputs (
    run_id        TEXT NOT NULL REFERENCES runs (run_id),
    stage_id      TEXT NOT NULL,
    output_type   TEXT NOT NULL,
    output_json   TEXT NOT NULL,
    used_fallback TEXT,
    PRIMARY KEY (run_id, stage_id)
);
"""

EVENT: TypeAdapter[Event] = TypeAdapter(Event)

Subscriber = Callable[[Event], None]


def open_db(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    if str(path) != ":memory:":
        db.execute("PRAGMA journal_mode = WAL")  # readers (the API) never block the runner
    db.executescript(SCHEMA)
    return db


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    status: str
    today: str
    config_hash: str
    started_at: str | None  # ts of the run.started event
    totals: dict[str, int]  # from run.completed; empty while running


class EventLog:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db
        self._next_seq: dict[str, int] = {}
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.append(subscriber)

    # --- runs ---------------------------------------------------------------------

    def start_run(self, run_id: str, config_hash: str, today: str) -> None:
        self._db.execute(
            "INSERT INTO runs (run_id, config_hash, today, status) VALUES (?, ?, ?, 'running')",
            (run_id, config_hash, today),
        )
        self._db.commit()
        self._next_seq[run_id] = 0

    def finish_run(self, run_id: str, status: str) -> None:
        self._db.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
        self._db.commit()

    # --- events -------------------------------------------------------------------

    def append(
        self, run_id: str, event_type: type[EventBase], payload: BaseModel, *, fixture: bool = False
    ) -> Event:
        seq = self._next_seq[run_id]
        event: Event = EVENT.validate_python(
            {
                "type": event_type.model_fields["type"].default,
                "run_id": run_id,
                "seq": seq,
                "ts": datetime.now(UTC),
                "fixture": fixture,
                "payload": payload,
            }
        )
        self._insert(event)
        self._db.commit()
        self._next_seq[run_id] = seq + 1
        for subscriber in self._subscribers:
            subscriber(event)
        return event

    def _insert(self, event: Event) -> None:
        self._db.execute(
            "INSERT INTO events (run_id, seq, type, payload_json, ts, fixture) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.run_id,
                event.seq,
                event.type,
                event.payload.model_dump_json(),
                event.ts.isoformat(),
                int(event.fixture),
            ),
        )

    def events(self, run_id: str, *, from_seq: int = 0) -> list[Event]:
        rows = self._db.execute(
            "SELECT run_id, seq, type, payload_json, ts, fixture FROM events "
            "WHERE run_id = ? AND seq >= ? ORDER BY seq",
            (run_id, from_seq),
        ).fetchall()
        return [
            EVENT.validate_python(
                {
                    "run_id": r[0],
                    "seq": r[1],
                    "type": r[2],
                    "payload": json.loads(r[3]),
                    "ts": r[4],
                    "fixture": bool(r[5]),
                }
            )
            for r in rows
        ]

    def run_info(self, run_id: str) -> RunInfo | None:
        infos = self._run_infos("WHERE r.run_id = ?", (run_id,))
        return infos[0] if infos else None

    def list_runs(self, limit: int = 50) -> list[RunInfo]:
        return self._run_infos("ORDER BY r.rowid DESC LIMIT ?", (limit,))

    def _run_infos(self, clause: str, params: tuple[object, ...]) -> list[RunInfo]:
        rows = self._db.execute(
            "SELECT r.run_id, r.status, r.today, r.config_hash, "
            "  (SELECT ts FROM events WHERE run_id = r.run_id AND seq = 0), "
            "  (SELECT payload_json FROM events "
            "   WHERE run_id = r.run_id AND type = 'run.completed') "
            f"FROM runs r {clause}",
            params,
        ).fetchall()
        return [
            RunInfo(
                run_id=r[0],
                status=r[1],
                today=r[2],
                config_hash=r[3],
                started_at=r[4],
                totals=json.loads(r[5])["totals"] if r[5] else {},
            )
            for r in rows
        ]

    def import_run(self, events: list[Event]) -> bool:
        """Store a recorded run (e.g. from data/runs/) as-is. False if it already exists."""
        first, last = events[0], events[-1]
        if first.type != "run.started" or last.type != "run.completed":
            raise ValueError(
                "a recorded run must start with run.started and end with run.completed"
            )
        if self.run_info(first.run_id) is not None:
            return False
        with self._db:
            self._db.execute(
                "INSERT INTO runs (run_id, config_hash, today, status) VALUES (?, ?, ?, ?)",
                (
                    first.run_id,
                    first.payload.config_hash,
                    first.payload.today.isoformat(),
                    last.payload.status,
                ),
            )
            for event in events:
                if event.run_id != first.run_id:
                    raise ValueError("a recorded run must contain a single run_id")
                self._insert(event)
        return True

    # --- stage outputs ------------------------------------------------------------

    def record_stage_output(
        self, run_id: str, stage_id: str, output: StageOutput, used_fallback: str | None
    ) -> None:
        value = output.value
        output_type = (
            "" if value is None else f"{type(value).__module__}:{type(value).__qualname__}"
        )
        self._db.execute(
            "INSERT INTO stage_outputs "
            "(run_id, stage_id, output_type, output_json, used_fallback) VALUES (?, ?, ?, ?, ?)",
            (run_id, stage_id, output_type, output.model_dump_json(), used_fallback),
        )
        self._db.commit()

    def last_stage_output(self, stage_id: str, *, exclude_run: str) -> StageOutput | None:
        """The latest output this stage produced without a fallback, in an earlier run."""
        row = self._db.execute(
            "SELECT so.output_type, so.output_json FROM stage_outputs so "
            "JOIN runs r ON r.run_id = so.run_id "
            "WHERE so.stage_id = ? AND so.used_fallback IS NULL AND so.run_id != ? "
            "ORDER BY r.rowid DESC LIMIT 1",
            (stage_id, exclude_run),
        ).fetchone()
        if row is None:
            return None
        output_type, output_json = row
        data: dict[str, Any] = json.loads(output_json)
        if output_type:
            data["value"] = _import_model(output_type).model_validate(data["value"])
        return StageOutput.model_validate(data)


def _import_model(qualified: str) -> type[BaseModel]:
    module_name, _, name = qualified.partition(":")
    cls = getattr(importlib.import_module(module_name), name)
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        raise TypeError(f"{qualified} is not a Pydantic model")
    return cls

"""The event log: append-only SQLite storage plus in-process publish.

Tables: runs, events (append-only, gapless seq per run, enforced by triggers),
effect_cache (see cache.py), and stage_outputs (each stage's output per run, the
source for the `last_recorded` fallback).
"""

import importlib
import json
import sqlite3
from collections.abc import Callable
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
    db.executescript(SCHEMA)
    return db


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
        self._db.execute(
            "INSERT INTO events (run_id, seq, type, payload_json, ts, fixture) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                seq,
                event.type,
                event.payload.model_dump_json(),
                event.ts.isoformat(),
                int(fixture),
            ),
        )
        self._db.commit()
        self._next_seq[run_id] = seq + 1
        for subscriber in self._subscribers:
            subscriber(event)
        return event

    def events(self, run_id: str) -> list[Event]:
        rows = self._db.execute(
            "SELECT run_id, seq, type, payload_json, ts, fixture FROM events "
            "WHERE run_id = ? ORDER BY seq",
            (run_id,),
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

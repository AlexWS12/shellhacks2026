import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue

from tandem_core import locate
from tandem_core.models import Event
from tandem_core.stage import (
    EffectRequest,
    NeedEffects,
    ReferenceResultList,
    StageContext,
    StageOutput,
    canonical_json,
)
from tandem_runner.config import PipelineConfig
from tandem_runner.dag import Runner
from tandem_runner.effects import EXECUTORS, Executor
from tandem_runner.events import EventLog, open_db

ROOT = Path(__file__).resolve().parents[3]

MakeRunner = Callable[..., Runner]
WithStage = Callable[..., PipelineConfig]

STAGES = [
    "extract_desc",
    "extract_ga",
    "load_reference",
    "locate",
    "validate",
    "overlap",
    "reference_test",
    "rank_and_cost",
    "briefs",
]


def events_of(
    make_runner: MakeRunner, config: PipelineConfig, **kw: Any
) -> tuple[str, list[Event]]:
    runner = make_runner(config, **kw)
    result = runner.run()
    return result.status, runner.log.events(result.run_id)


def completed(events: list[Event], stage_id: str) -> Any:
    return next(
        e.payload for e in events if e.type == "stage.completed" and e.payload.stage_id == stage_id
    )


def checks(events: list[Event]) -> list[Any]:
    return [e.payload for e in events if e.type == "check.raised"]


# --- CLI determinism ----------------------------------------------------------------


def _cli(db: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tandem_runner",
            "run",
            "--config",
            str(ROOT / "pipeline.yaml"),
            "--db",
            str(db),
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return [json.loads(line) for line in proc.stdout.splitlines()]


def _normalize(event: dict[str, Any]) -> dict[str, Any]:
    """Drop fields that legitimately differ between runs (NFR-2 / ADR-012)."""
    event = {k: v for k, v in event.items() if k not in ("ts", "run_id")}
    if event["type"] == "stage.completed":
        event["payload"] = {k: v for k, v in event["payload"].items() if k != "duration_ms"}
    return event


def test_cli_twice_gives_same_event_sequence(tmp_path: Path) -> None:
    first, second = _cli(tmp_path / "t.db"), _cli(tmp_path / "t.db")
    assert [e["seq"] for e in first] == list(range(len(first)))
    assert first[0]["type"] == "run.started" and first[-1]["type"] == "run.completed"
    assert first[-1]["payload"]["status"] == "completed"
    assert [_normalize(e) for e in first] == [_normalize(e) for e in second]
    assert first[0]["run_id"] != second[0]["run_id"]


def test_cli_emits_the_fixture(tmp_path: Path) -> None:
    events = _cli(tmp_path / "t.db")
    fixture = [(e["type"], e["payload"].get("id")) for e in events if e["fixture"]]
    assert ("record.extracted", "DESC_3") in fixture
    assert ("record.extracted", "GPC_2") in fixture
    overlap = next(e["payload"] for e in events if e["type"] == "overlap.found")
    assert (overlap["distance_mi"], overlap["gap_days"]) == (5.65, 152)
    lifecycle = [e for e in events if e["type"].startswith(("run.", "stage."))]
    assert not any(e["fixture"] for e in lifecycle)


# --- Timeouts and fallbacks ---------------------------------------------------------


def _slow_overpass(request: EffectRequest) -> JsonValue:
    time.sleep(1.0)
    return {"elements": []}


def _slow_resolve(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    time.sleep(1.0)
    return locate.resolve(ctx, inputs, effects)


def test_timeout_without_recorded_run_degrades_to_town_gazetteer(
    make_runner: MakeRunner, config: PipelineConfig, with_stage: WithStage
) -> None:
    slow = with_stage(config, "locate", timeout_s=0.2)
    executors: dict[str, Executor] = {**EXECUTORS, "overpass": _slow_overpass}
    started = time.monotonic()
    status, events = events_of(make_runner, slow, executors=executors)

    assert time.monotonic() - started < 1.0, "runner waited for the slow effect"
    assert status == "completed"
    assert completed(events, "locate").used_fallback == "town_gazetteer"
    raised = [(c.rule_id, c.severity, c.subject) for c in checks(events)]
    assert raised == [
        ("RUN-TIMEOUT", "warn", "locate"),
        ("RUN-FALLBACK-UNAVAILABLE", "warn", "locate"),
    ]
    assert "last_recorded" in checks(events)[1].message
    # Downstream stages still ran on the fallback output.
    assert completed(events, "briefs").used_fallback is None


def test_timeout_uses_last_recorded_output(
    make_runner: MakeRunner, config: PipelineConfig, with_stage: WithStage
) -> None:
    status, baseline = events_of(make_runner, config)
    assert status == "completed"
    assert completed(baseline, "locate").used_fallback is None

    slow = with_stage(config, "locate", timeout_s=0.2)
    status, events = events_of(
        make_runner, slow, overrides={"tandem_core.locate.resolve": _slow_resolve}
    )
    assert status == "completed"
    locate_done = completed(events, "locate")
    assert locate_done.used_fallback == "last_recorded"
    assert locate_done.counts == completed(baseline, "locate").counts
    assert [c.rule_id for c in checks(events)] == ["RUN-TIMEOUT"]
    final, reference = events[-1], baseline[-1]
    assert final.type == "run.completed" and reference.type == "run.completed"
    assert final.payload.output_hashes == reference.payload.output_hashes


def test_briefs_fall_back_to_template_when_llm_fails(
    make_runner: MakeRunner, config: PipelineConfig
) -> None:
    def broken(request: EffectRequest) -> JsonValue:
        raise ConnectionError("gemini unreachable")

    status, events = events_of(
        make_runner, config, executors={**EXECUTORS, "llm_structured": broken}
    )
    assert status == "completed"
    assert completed(events, "briefs").used_fallback == "template"
    brief = next(e.payload.brief for e in events if e.type == "brief.written")
    assert brief.source == "template"
    assert "gemini unreachable" in checks(events)[0].message


# --- Gates and failures -------------------------------------------------------------


def _failing_reference(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    return StageOutput(
        value=ReferenceResultList(results=()),
        counts={"reference.passed": 5, "reference.total": 6},
    )


def test_gate_failure_fails_the_run(make_runner: MakeRunner, config: PipelineConfig) -> None:
    status, events = events_of(
        make_runner, config, overrides={"tandem_core.overlap.test_reference": _failing_reference}
    )
    assert status == "failed"
    started = [e.payload.stage_id for e in events if e.type == "stage.started"]
    assert started == STAGES[: STAGES.index("reference_test") + 1]
    gate = checks(events)[-1]
    assert (gate.rule_id, gate.severity) == ("RUN-GATE", "error")
    assert "reference.passed=5" in gate.message
    assert events[-1].type == "run.completed" and events[-1].payload.status == "failed"


def test_undeclared_effect_fails_stage_without_fallback(
    make_runner: MakeRunner, config: PipelineConfig
) -> None:
    def sneaky(
        ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
    ) -> StageOutput | NeedEffects:
        return NeedEffects(requests=(EffectRequest(kind="nominatim", params={"q": "x"}),))

    status, events = events_of(
        make_runner, config, overrides={"tandem_core.parse_desc.parse": sneaky}
    )
    assert status == "failed"
    rules = [(c.rule_id, c.severity) for c in checks(events)]
    assert rules == [("RUN-STAGE-ERROR", "error"), ("RUN-STAGE-FAILED", "error")]
    assert "not declared" in checks(events)[0].message


# --- Effects and cache --------------------------------------------------------------


def test_effect_key_is_sha256_of_canonical_request() -> None:
    request = EffectRequest(kind="overpass", params={"utility": "GPC", "bbox": [1, 2]})
    expected = hashlib.sha256(
        canonical_json({"kind": "overpass", "params": {"bbox": [1, 2], "utility": "GPC"}}).encode()
    ).hexdigest()
    assert request.key == expected


def test_second_run_is_served_from_effect_cache(
    make_runner: MakeRunner, config: PipelineConfig, tmp_path: Path
) -> None:
    calls: list[str] = []

    def counting(kind: str) -> Executor:
        def run(request: EffectRequest) -> JsonValue:
            calls.append(kind)
            return EXECUTORS[kind](request)

        return run

    executors = {kind: counting(kind) for kind in EXECUTORS}
    events_of(make_runner, config, executors=executors)
    first = sorted(calls)
    assert first == sorted(
        ["read_pdf_text", "read_pdf_text", "read_xlsx", "overpass", "overpass", "llm_structured"]
    )
    calls.clear()
    events_of(make_runner, config, executors=executors)
    assert calls == []

    db = sqlite3.connect(tmp_path / "tandem.db")
    rows = db.execute("SELECT hash, request_json FROM effect_cache").fetchall()
    assert len(rows) == len(first)
    for key, request_json in rows:
        assert key == hashlib.sha256(request_json.encode()).hexdigest()


# --- Event log ----------------------------------------------------------------------


def test_events_are_append_only_and_gapless(
    make_runner: MakeRunner, config: PipelineConfig, tmp_path: Path
) -> None:
    runner = make_runner(config)
    run_id = runner.run().run_id
    db = sqlite3.connect(tmp_path / "tandem.db")
    rows = db.execute("SELECT seq FROM events WHERE run_id = ? ORDER BY seq", (run_id,))
    seqs = [r[0] for r in rows]
    assert seqs == list(range(len(seqs)))

    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("UPDATE events SET type = 'x' WHERE run_id = ?", (run_id,))
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        db.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
    with pytest.raises(sqlite3.DatabaseError, match="gapless"):
        db.execute(
            "INSERT INTO events (run_id, seq, type, payload_json, ts) "
            "VALUES (?, ?, 'x', '{}', 't')",
            (run_id, len(seqs) + 1),
        )


def test_event_log_round_trips_events(make_runner: MakeRunner, config: PipelineConfig) -> None:
    seen: list[Event] = []
    runner = make_runner(config)
    runner.log.subscribe(seen.append)
    run_id = runner.run().run_id
    assert runner.log.events(run_id) == seen


def test_open_db_is_idempotent(tmp_path: Path) -> None:
    open_db(tmp_path / "a.db").close()
    EventLog(open_db(tmp_path / "a.db"))


# --- today --------------------------------------------------------------------------


def test_today_comes_from_config(make_runner: MakeRunner, config: PipelineConfig) -> None:
    seen: list[date] = []

    def spy(
        ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
    ) -> StageOutput | NeedEffects:
        seen.append(ctx.run.today)
        return StageOutput(value=inputs["overlaps"], counts={})

    later = config.model_copy(
        update={"run": config.run.model_copy(update={"today": date(2030, 1, 2)})}
    )
    rank_stage = next(s for s in later.stages if s.id == "rank_and_cost")
    assert rank_stage.fn == "tandem_core.rank.rank_with_costs"
    _, events = events_of(make_runner, later, overrides={"tandem_core.rank.rank_with_costs": spy})
    assert seen == [date(2030, 1, 2)]
    first = events[0]
    assert first.type == "run.started"
    assert first.payload.today == date(2030, 1, 2)

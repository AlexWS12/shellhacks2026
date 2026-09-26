"""Write the reducer parity fixtures to packages/contracts/fixtures/reducer/.

For each event log (every recorded run in data/runs/, plus a synthetic edge-case log
written here) this writes `<name>.state.json`: tandem_core.reduce.fold of the log.
pytest checks the Python reducer against these files and vitest checks
apps/web/lib/reducer.ts against the same files, so the two reducers cannot drift.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from tandem_core import fixtures
from tandem_core.models import (
    Brief,
    BriefWritten,
    BriefWrittenPayload,
    Check,
    CheckRaised,
    Endpoint,
    EndpointLocated,
    EndpointLocatedPayload,
    Event,
    EventBase,
    Location,
    OverlapFound,
    Provenance,
    RecordExtracted,
    ReferenceTested,
    RunCompleted,
    RunCompletedPayload,
    RunStarted,
    RunStartedPayload,
    StageCompleted,
    StageCompletedPayload,
    StageStarted,
    StageStartedPayload,
)
from tandem_core.reduce import fold

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
OUT = ROOT / "packages" / "contracts" / "fixtures" / "reducer"
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def edge_cases() -> list[Event]:
    """Every event type, endpoint replace/append, an unknown project, re-ranking, a failure."""
    t0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    events: list[Event] = []

    def add(kind: type[EventBase], payload: BaseModel, fixture: bool = True) -> None:
        seq = len(events)
        events.append(
            EVENT.validate_python(
                {
                    "type": kind.model_fields["type"].default,
                    "run_id": "edge-cases",
                    "seq": seq,
                    "ts": t0 + timedelta(milliseconds=250 * seq),
                    "fixture": fixture,
                    "payload": payload,
                }
            )
        )

    located = Location(lat=32.35, lon=-81.08, method="overpass", confidence="high", evidence="n1")
    jasper = Endpoint(raw_name="JASPER", name="Jasper", location=None, unlocated_reason="pending")
    okatie = Endpoint(raw_name="OKATIE", name="Okatie", location=located, unlocated_reason=None)
    project = fixtures.DESC_3.model_copy(update={"endpoints": (jasper,), "partial_location": True})
    near = fixtures.OVERLAP
    far = near.model_copy(update={"id": "far", "distance_mi": 20.25, "in_reference": False})
    tie = near.model_copy(update={"id": "tie", "gap_days": 10, "confidence": "town"})
    prov = Provenance(file="pipeline.yaml", page=None, locator="stage locate", stage="locate")

    add(
        RunStarted,
        RunStartedPayload(config_hash="edge", input_hashes={"desc_pdf": "h"}, today=t0.date()),
        fixture=False,
    )
    add(StageStarted, StageStartedPayload(stage_id="extract_desc"), fixture=False)
    add(RecordExtracted, project)
    add(RecordExtracted, fixtures.GPC_2)
    add(
        StageCompleted,
        StageCompletedPayload(
            stage_id="extract_desc", counts={"projects": 2}, duration_ms=5, used_fallback=None
        ),
        fixture=False,
    )
    add(StageStarted, StageStartedPayload(stage_id="locate"), fixture=False)
    add(
        EndpointLocated,
        EndpointLocatedPayload(
            project_id="DESC_3",
            endpoint=jasper.model_copy(update={"location": located, "unlocated_reason": None}),
        ),
    )
    add(EndpointLocated, EndpointLocatedPayload(project_id="DESC_3", endpoint=okatie))
    add(EndpointLocated, EndpointLocatedPayload(project_id="NOPE", endpoint=okatie))
    add(
        CheckRaised,
        Check(
            rule_id="RUN-TIMEOUT",
            severity="warn",
            subject="locate",
            message="slow",
            provenance=prov,
        ),
        fixture=False,
    )
    add(
        StageCompleted,
        StageCompletedPayload(
            stage_id="locate", counts={"projects": 2}, duration_ms=90, used_fallback="last_recorded"
        ),
        fixture=False,
    )
    add(OverlapFound, far)
    add(OverlapFound, near)
    add(
        BriefWritten,
        BriefWrittenPayload(
            overlap_id=near.id,
            brief=Brief(
                dominion_position="Dominion builds first.",
                georgia_position="Georgia needs it by June.",
                mediator_summary="Share the river crossing survey.",
                shareable=("survey",),
                cited_fields=("DESC_3.in_service", "GPC_2.in_service"),
                source="template",
            ),
        ),
    )
    add(OverlapFound, tie)
    add(ReferenceTested, fixtures.REFERENCE_RESULT)
    add(StageStarted, StageStartedPayload(stage_id="reference_test"), fixture=False)
    add(
        RunCompleted,
        RunCompletedPayload(status="failed", totals={"events": 18}, output_hashes={}),
        fixture=False,
    )
    return events


def dump_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    out: Path = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.json*"):
        stale.unlink()

    logs: dict[str, list[Event]] = {}
    for path in sorted(RUNS.glob("*.jsonl")):
        lines = path.read_text(encoding="utf-8").splitlines()
        logs[path.stem] = [EVENT.validate_json(line) for line in lines if line]
    edge = edge_cases()
    logs["edge-cases"] = edge
    (out / "edge-cases.jsonl").write_text(
        "".join(EVENT.dump_json(e).decode() + "\n" for e in edge), encoding="utf-8"
    )
    for name, events in logs.items():
        state = fold(events).model_dump(mode="json")
        (out / f"{name}.state.json").write_text(dump_json(state), encoding="utf-8")
    print(f"wrote {len(logs)} reducer fixtures to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from tandem_core import fixtures
from tandem_core.models import (
    Brief,
    BriefWritten,
    BriefWrittenPayload,
    Endpoint,
    EndpointLocated,
    EndpointLocatedPayload,
    Event,
    Location,
    OverlapFound,
    RecordExtracted,
    RunCompleted,
    RunCompletedPayload,
)
from tandem_core.reduce import INITIAL, fold, reduce

ROOT = Path(__file__).resolve().parents[3]
EVENT: TypeAdapter[Event] = TypeAdapter(Event)
TS = datetime(2026, 9, 26, tzinfo=UTC)


def recorded(name: str = "stub-1.jsonl") -> list[Event]:
    text = (ROOT / "data" / "runs" / name).read_text(encoding="utf-8")
    return [EVENT.validate_json(line) for line in text.splitlines() if line]


def test_fold_of_nothing_is_initial() -> None:
    assert fold([]) == INITIAL


def test_fold_recorded_stub_run() -> None:
    events = recorded()
    state = fold(events)
    assert state.run_id == events[0].run_id
    assert state.status == "completed"
    assert set(state.projects) == {"DESC_3", "GPC_2"}
    assert len(state.stages) == 9
    assert all(s.status == "completed" for s in state.stages.values())
    assert state.stages["reference_test"].counts == {"reference.passed": 1, "reference.total": 1}
    assert list(state.overlaps) == ["DESC_3~GPC_2"]
    assert [r.passed for r in state.reference_results] == [True]
    (opportunity,) = state.opportunities
    assert opportunity.rank == 1
    assert opportunity.brief is not None
    assert state.totals == events[-1].payload.totals  # type: ignore[union-attr]


def test_reduce_returns_new_state_and_leaves_old_one_alone() -> None:
    before = INITIAL
    after = reduce(before, RecordExtracted(run_id="r", seq=0, ts=TS, payload=fixtures.DESC_3))
    assert before.projects == {}
    assert after.projects == {"DESC_3": fixtures.DESC_3}


def test_stage_lifecycle_and_fallback() -> None:
    events = recorded()
    started_only = fold(e for e in events if e.type != "stage.completed")
    assert all(s.status == "running" for s in started_only.stages.values())


def test_endpoint_located_replaces_or_appends() -> None:
    location = Location(lat=1.0, lon=2.0, method="overpass", confidence="high", evidence="osm:1")
    unlocated = Endpoint(raw_name="JASPER", name="Jasper", location=None, unlocated_reason="?")
    project = fixtures.DESC_3.model_copy(update={"endpoints": (unlocated,)})
    state = reduce(INITIAL, RecordExtracted(run_id="r", seq=0, ts=TS, payload=project))

    def located(endpoint: Endpoint, project_id: str = "DESC_3") -> EndpointLocated:
        payload = EndpointLocatedPayload(project_id=project_id, endpoint=endpoint)
        return EndpointLocated(run_id="r", seq=1, ts=TS, payload=payload)

    jasper = unlocated.model_copy(update={"location": location, "unlocated_reason": None})
    okatie = Endpoint(raw_name="OKATIE", name="Okatie", location=location, unlocated_reason=None)
    state = reduce(state, located(jasper))
    state = reduce(state, located(okatie))
    assert state.projects["DESC_3"].endpoints == (jasper, okatie)
    assert reduce(state, located(okatie, project_id="nope")) == state


def test_opportunities_rank_by_distance_then_gap_and_keep_briefs() -> None:
    near = fixtures.OVERLAP
    far = near.model_copy(update={"id": "far", "distance_mi": 20.0})
    tie = near.model_copy(update={"id": "tie", "gap_days": 10})
    brief = Brief(
        dominion_position="d",
        georgia_position="g",
        mediator_summary="m",
        shareable=(),
        cited_fields=(),
        source="template",
    )
    state = fold(
        [
            OverlapFound(run_id="r", seq=0, ts=TS, payload=far),
            OverlapFound(run_id="r", seq=1, ts=TS, payload=near),
            BriefWritten(
                run_id="r",
                seq=2,
                ts=TS,
                payload=BriefWrittenPayload(overlap_id=near.id, brief=brief),
            ),
            OverlapFound(run_id="r", seq=3, ts=TS, payload=tie),
        ]
    )
    assert [(o.rank, o.overlap.id) for o in state.opportunities] == [
        (1, "tie"),
        (2, near.id),
        (3, "far"),
    ]
    assert state.opportunities[1].brief == brief


def test_failed_run() -> None:
    payload = RunCompletedPayload(status="failed", totals={"x": 1}, output_hashes={})
    state = reduce(INITIAL, RunCompleted(run_id="r", seq=0, ts=TS, payload=payload))
    assert (state.status, state.totals) == ("failed", {"x": 1})

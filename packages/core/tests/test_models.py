from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from tandem_core.models import (
    Brief,
    BriefWritten,
    BriefWrittenPayload,
    Check,
    Endpoint,
    Event,
    Location,
    Overlap,
    OverlapFound,
    Project,
    Provenance,
    RecordExtracted,
)

PROV = Provenance(
    file="2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf",
    page=12,
    locator="TEAMS 20277, zone 219",
    stage="extract_ga",
)
LOCATION = Location(
    lat=32.352116, lon=-81.175112, method="sponsor", confidence="verified", evidence="sponsor"
)
ENDPOINT = Endpoint(raw_name="MCINTOSH", name="McIntosh", location=LOCATION, unlocated_reason=None)
PROJECT = Project(
    id="GPC_2",
    utility="GPC",
    sponsor="SAV",
    name="SAV: MCINTOSH - PURRYSBURG 230KV REACTORS",
    description="",
    status=None,
    in_service=date(2026, 6, 1),
    build_start=None,
    cost_total=None,
    cost_by_year=None,
    length_mi=None,
    endpoints=(ENDPOINT,),
    center=(32.352116, -81.175112),
    confidence="verified",
    partial_location=True,
    provenance=PROV,
)
OVERLAP = Overlap(
    id="DESC_3~GPC_2",
    a="DESC_3",
    b="GPC_2",
    distance_mi=5.65,
    closest_mi=None,
    gap_days=152,
    windows_overlap=True,
    confidence="verified",
    in_reference=True,
)
CHECK = Check(rule_id="V-10", severity="info", subject="GPC_2", message="REDACTED", provenance=PROV)
TS = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

RECORDS = [PROV, LOCATION, ENDPOINT, PROJECT, OVERLAP, CHECK]
EVENTS: list[Event] = [
    RecordExtracted(run_id="r1", seq=1, ts=TS, fixture=True, payload=PROJECT),
    OverlapFound(run_id="r1", seq=2, ts=TS, fixture=True, payload=OVERLAP),
    BriefWritten(
        run_id="r1",
        seq=3,
        ts=TS,
        payload=BriefWrittenPayload(
            overlap_id=OVERLAP.id,
            brief=Brief(
                dominion_position="d",
                georgia_position="g",
                mediator_summary="m",
                shareable=("right of way",),
                cited_fields=("GPC_2.in_service",),
                source="template",
            ),
        ),
    ),
]
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: type(r).__name__)
def test_assignment_raises(record: BaseModel) -> None:
    field = next(iter(type(record).model_fields))
    with pytest.raises(ValidationError):
        setattr(record, field, None)


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: type(r).__name__)
def test_record_json_round_trip(record: BaseModel) -> None:
    assert type(record).model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("event", EVENTS, ids=lambda e: e.type)
def test_event_json_round_trip_through_union(event: Event) -> None:
    parsed = EVENT.validate_json(EVENT.dump_json(event))
    assert type(parsed) is type(event)
    assert parsed == event


def test_event_json_always_carries_type_and_fixture() -> None:
    raw = EVENT.dump_python(EVENTS[2], mode="json")
    assert raw["type"] == "brief.written"
    assert raw["fixture"] is False


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValidationError):
        EVENT.validate_python({"type": "nope", "run_id": "r", "seq": 0, "ts": TS, "payload": {}})


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate({**PROV.model_dump(), "extra": 1})

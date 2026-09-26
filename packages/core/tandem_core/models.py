"""The Tandem contract: frozen records and the event union.

Every model here is immutable. JSON Schema is exported from these classes and the
TypeScript types in packages/contracts/ts are generated from that schema, so change
a model here and run `make types`; never edit the generated files.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["verified", "high", "town", "low"]  # strongest to weakest
Severity = Literal["error", "warn", "info"]


class Frozen(BaseModel):
    # Serialization-mode schemas mark defaulted fields (event `type`, `fixture`) as
    # required, since they are always present on the wire; TS narrowing depends on it.
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )


# --- Core records -----------------------------------------------------------------


class Provenance(Frozen):
    file: str  # "2025 IRP Volume 3 PUBLIC DISCLOSURE.pdf"
    page: int | None
    locator: str  # "ID 06367 D-G" or "TEAMS 20277, zone 219"
    stage: str  # stage id that produced the value


class Location(Frozen):
    lat: float
    lon: float
    method: Literal["sponsor", "overpass", "nominatim", "town", "agent"]
    confidence: Confidence
    evidence: str  # OSM id, query, or reason


class Endpoint(Frozen):
    raw_name: str
    name: str
    location: Location | None
    unlocated_reason: str | None


class Project(Frozen):
    id: str  # "DESC-06367D-G" | "GA-20277"
    utility: str  # a utility id declared under `utilities:` in pipeline.yaml
    sponsor: str  # DESC | GPC | SAV | GTC | MEAG | DU
    name: str
    description: str
    status: str | None
    in_service: date  # the source's declared in_service field
    build_start: date | None  # informational only; never used in gap_days
    cost_total: int | None
    cost_by_year: dict[str, int] | None
    length_mi: float | None
    endpoints: tuple[Endpoint, ...]
    center: tuple[float, float] | None  # (lat, lon)
    confidence: Confidence | None  # weakest of the located endpoints; None if none located
    partial_location: bool  # True when any endpoint is unlocated
    provenance: Provenance


class Overlap(Frozen):
    id: str
    a: str  # project id from the first utility of its pair
    b: str
    distance_mi: float  # center to center, haversine, 2 decimals
    closest_mi: float | None  # extra: nearest points of lines
    gap_days: int
    windows_overlap: bool
    confidence: Confidence  # weaker of the two projects
    in_reference: bool


class Check(Frozen):
    rule_id: str
    severity: Severity
    subject: str  # project id or file
    message: str
    provenance: Provenance


# --- Supporting models ------------------------------------------------------------


class ReferenceSet(Frozen):
    projects: tuple[Project, ...]
    overlaps: tuple[Overlap, ...]
    verified_coords: dict[str, tuple[float, float]]  # endpoint name -> (lat, lon)


class ReferenceResult(Frozen):
    pair: tuple[str, str]
    expected_mi: float
    actual_mi: float | None
    expected_days: int
    actual_days: int | None
    passed: bool


class CostAssumption(Frozen):
    name: str
    value: float | str
    source: str
    url: str | None


class CostEstimate(Frozen):
    low: int
    high: int
    currency: str  # "USD"
    assumptions: tuple[CostAssumption, ...]


class Brief(Frozen):
    dominion_position: str
    georgia_position: str
    mediator_summary: str
    shareable: tuple[str, ...]
    cited_fields: tuple[str, ...]  # "<project id>.<field>"
    source: Literal["llm", "template"]


class Opportunity(Frozen):
    overlap: Overlap
    rank: int
    windows_overlap: bool
    cost_estimate: CostEstimate | None
    brief: Brief | None


class StageState(Frozen):
    status: Literal["pending", "running", "completed", "failed"]
    counts: dict[str, int]
    used_fallback: str | None


class RunState(Frozen):
    run_id: str
    status: Literal["running", "completed", "failed"]
    stages: dict[str, StageState]
    projects: dict[str, Project]
    checks: tuple[Check, ...]
    overlaps: dict[str, Overlap]
    reference_results: tuple[ReferenceResult, ...]
    opportunities: tuple[Opportunity, ...]
    totals: dict[str, int]


# --- Event payloads ---------------------------------------------------------------


class RunStartedPayload(Frozen):
    config_hash: str
    input_hashes: dict[str, str]  # source id -> content hash
    today: date


class StageStartedPayload(Frozen):
    stage_id: str


class StageCompletedPayload(Frozen):
    stage_id: str
    counts: dict[str, int]
    duration_ms: int
    used_fallback: str | None


class EndpointLocatedPayload(Frozen):
    project_id: str
    endpoint: Endpoint


class BriefWrittenPayload(Frozen):
    overlap_id: str
    brief: Brief


class RunCompletedPayload(Frozen):
    totals: dict[str, int]
    output_hashes: dict[str, str]


# --- Events -----------------------------------------------------------------------


class EventBase(Frozen):
    run_id: str
    seq: int = Field(ge=0)  # ordered within a run
    ts: datetime
    fixture: bool = False  # True for scaffold stub data


class RunStarted(EventBase):
    type: Literal["run.started"] = "run.started"
    payload: RunStartedPayload


class StageStarted(EventBase):
    type: Literal["stage.started"] = "stage.started"
    payload: StageStartedPayload


class StageCompleted(EventBase):
    type: Literal["stage.completed"] = "stage.completed"
    payload: StageCompletedPayload


class RecordExtracted(EventBase):
    type: Literal["record.extracted"] = "record.extracted"
    payload: Project


class EndpointLocated(EventBase):
    type: Literal["endpoint.located"] = "endpoint.located"
    payload: EndpointLocatedPayload


class CheckRaised(EventBase):
    type: Literal["check.raised"] = "check.raised"
    payload: Check


class OverlapFound(EventBase):
    type: Literal["overlap.found"] = "overlap.found"
    payload: Overlap


class ReferenceTested(EventBase):
    type: Literal["reference.tested"] = "reference.tested"
    payload: ReferenceResult


class BriefWritten(EventBase):
    type: Literal["brief.written"] = "brief.written"
    payload: BriefWrittenPayload


class RunCompleted(EventBase):
    type: Literal["run.completed"] = "run.completed"
    payload: RunCompletedPayload


Event = Annotated[
    RunStarted
    | StageStarted
    | StageCompleted
    | RecordExtracted
    | EndpointLocated
    | CheckRaised
    | OverlapFound
    | ReferenceTested
    | BriefWritten
    | RunCompleted,
    Field(discriminator="type"),
]

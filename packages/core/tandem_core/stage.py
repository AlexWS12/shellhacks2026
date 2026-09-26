"""The stage protocol shared by core stage functions and the runner.

A stage function is pure: it receives a StageContext, its named inputs, and the
results of any effects it asked for so far, and returns either NeedEffects (more
outside-world data is required) or a StageOutput. The runner executes requested
effects, caches them by EffectRequest.key, and calls the function again.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Protocol

from pydantic import Field, JsonValue

from tandem_core.models import (
    BriefWrittenPayload,
    Check,
    EndpointLocatedPayload,
    Frozen,
    Opportunity,
    Overlap,
    Project,
    ReferenceResult,
)


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace: the form every hash in Tandem is computed over."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class EffectRequest(Frozen):
    """A request for the outside world, e.g. EffectRequest(kind="overpass", params={...})."""

    kind: str
    params: dict[str, JsonValue]

    @property
    def key(self) -> str:
        """SHA-256 of the canonical request JSON; the effect cache key."""
        return hashlib.sha256(canonical_json(self.model_dump(mode="json")).encode()).hexdigest()


class NeedEffects(Frozen):
    requests: tuple[EffectRequest, ...]


# Values a stage may emit; the runner wraps each in the matching event type.
Emit = Project | Check | Overlap | ReferenceResult | EndpointLocatedPayload | BriefWrittenPayload


class StageOutput(Frozen):
    value: Any = None  # bound to the stage's `out` name; a Frozen model or None
    emits: tuple[Emit, ...] = ()
    counts: dict[str, int] = Field(default_factory=dict)
    fixture: bool = False  # True while the stage returns scaffold stub data


class Source(Frozen):
    id: str
    path: str
    utility: str | None = None
    in_service_field: str | None = None


class RunParams(Frozen):
    today: date  # from pipeline.yaml run.today; never read from the clock
    distance_threshold_mi: float
    georgia_sponsors: tuple[str, ...]
    utilities: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    llm_model: str


class StageContext(Frozen):
    stage_id: str
    run: RunParams
    params: dict[str, JsonValue] = Field(default_factory=dict)  # e.g. {"top_n": 5}


class StageFn(Protocol):
    def __call__(
        self,
        ctx: StageContext,
        inputs: Mapping[str, Any],
        effects: Mapping[str, JsonValue],
    ) -> StageOutput | NeedEffects: ...


# --- Stage output values ----------------------------------------------------------
# Each `out` is one Frozen model so the runner can store and restore it by type name.


class ProjectList(Frozen):
    projects: tuple[Project, ...]


class CheckList(Frozen):
    checks: tuple[Check, ...]


class OverlapList(Frozen):
    overlaps: tuple[Overlap, ...]


class ReferenceResultList(Frozen):
    results: tuple[ReferenceResult, ...]


class OpportunityList(Frozen):
    opportunities: tuple[Opportunity, ...]


def missing(requests: tuple[EffectRequest, ...], effects: Mapping[str, JsonValue]) -> NeedEffects:
    """NeedEffects for the requests that have no result yet (empty if all are present)."""
    return NeedEffects(requests=tuple(r for r in requests if r.key not in effects))

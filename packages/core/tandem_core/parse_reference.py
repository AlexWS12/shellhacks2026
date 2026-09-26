"""Sponsor sample xlsx -> ReferenceSet. Stub until M1."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core import fixtures
from tandem_core.models import ReferenceSet
from tandem_core.stage import EffectRequest, NeedEffects, Source, StageContext, StageOutput, missing


def parse(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    source: Source = inputs["reference_xlsx"]
    need = missing((EffectRequest(kind="read_xlsx", params={"path": source.path}),), effects)
    if need.requests:
        return need
    reference = ReferenceSet(
        projects=(fixtures.DESC_3, fixtures.GPC_2),
        overlaps=(fixtures.OVERLAP,),
        verified_coords={},
    )
    return StageOutput(
        value=reference,
        counts={"projects": len(reference.projects), "overlaps": len(reference.overlaps)},
        fixture=True,
    )

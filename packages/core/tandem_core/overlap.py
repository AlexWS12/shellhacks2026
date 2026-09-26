"""Located projects -> Overlap[], and the sponsor reference test. Stub until M1."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core import fixtures
from tandem_core.stage import (
    NeedEffects,
    OverlapList,
    ReferenceResultList,
    StageContext,
    StageOutput,
)


def find(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    overlaps = (fixtures.OVERLAP,)
    return StageOutput(
        value=OverlapList(overlaps=overlaps),
        emits=overlaps,
        counts={"overlaps": len(overlaps)},
        fixture=True,
    )


def test_reference(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    results = (fixtures.REFERENCE_RESULT,)
    return StageOutput(
        value=ReferenceResultList(results=results),
        emits=results,
        counts={
            "reference.passed": sum(r.passed for r in results),
            "reference.total": len(results),
        },
        fixture=True,
    )

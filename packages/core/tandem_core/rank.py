"""Overlaps -> ranked Opportunity[] with cost estimates. Stub until M1."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core.models import Opportunity
from tandem_core.stage import NeedEffects, OpportunityList, OverlapList, StageContext, StageOutput


def rank_with_costs(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    overlaps: OverlapList = inputs["overlaps"]
    opportunities = tuple(
        Opportunity(
            overlap=o,
            rank=i,
            windows_overlap=o.windows_overlap,
            cost_estimate=None,
            brief=None,
        )
        for i, o in enumerate(overlaps.overlaps, start=1)
    )
    return StageOutput(
        value=OpportunityList(opportunities=opportunities),
        counts={"opportunities": len(opportunities)},
        fixture=True,
    )

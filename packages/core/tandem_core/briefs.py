"""Top opportunities -> briefs written by the LLM, or labeled templates. Stub until M2."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core.models import Brief, BriefWrittenPayload, Opportunity
from tandem_core.stage import (
    EffectRequest,
    NeedEffects,
    OpportunityList,
    StageContext,
    StageOutput,
    missing,
)


def _top(ctx: StageContext, inputs: Mapping[str, Any]) -> tuple[Opportunity, ...]:
    opportunities: OpportunityList = inputs["opportunities"]
    top_n = ctx.params.get("top_n", 5)
    assert isinstance(top_n, int)
    return opportunities.opportunities[:top_n]


def prompt_for(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    top = _top(ctx, inputs)
    requests = {
        o.overlap.id: EffectRequest(
            kind="llm_structured",
            params={"model": ctx.run.llm_model, "overlap_id": o.overlap.id},
        )
        for o in top
    }
    need = missing(tuple(requests.values()), effects)
    if need.requests:
        return need
    written = tuple(
        BriefWrittenPayload(
            overlap_id=overlap_id,
            brief=Brief.model_validate({**_as_dict(effects[r.key]), "source": "llm"}),
        )
        for overlap_id, r in requests.items()
    )
    return StageOutput(emits=written, counts={"briefs": len(written)}, fixture=True)


def fallback_template(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    written = tuple(
        BriefWrittenPayload(
            overlap_id=o.overlap.id,
            brief=Brief(
                dominion_position="Template: no LLM brief available.",
                georgia_position="Template: no LLM brief available.",
                mediator_summary=(
                    f"Projects {o.overlap.a} and {o.overlap.b} are "
                    f"{o.overlap.distance_mi} mi apart, {o.overlap.gap_days} days apart."
                ),
                shareable=(),
                cited_fields=(
                    f"{o.overlap.id}.distance_mi",
                    f"{o.overlap.id}.gap_days",
                ),
                source="template",
            ),
        )
        for o in _top(ctx, inputs)
    )
    return StageOutput(emits=written, counts={"briefs": len(written)}, fixture=True)


def _as_dict(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"llm_structured returned {type(value).__name__}, expected an object")
    return value

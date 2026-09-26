"""Georgia ten-year plan PDF -> Project[]. Stub until M1."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core import fixtures
from tandem_core.stage import (
    EffectRequest,
    NeedEffects,
    ProjectList,
    Source,
    StageContext,
    StageOutput,
    missing,
)


def parse(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    source: Source = inputs["ga_pdf"]
    need = missing((EffectRequest(kind="read_pdf_text", params={"path": source.path}),), effects)
    if need.requests:
        return need
    projects = (fixtures.GPC_2,)
    return StageOutput(
        value=ProjectList(projects=projects),
        emits=projects,
        counts={"projects": len(projects)},
        fixture=True,
    )

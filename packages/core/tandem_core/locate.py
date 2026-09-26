"""Endpoint candidates -> located projects. Stub until M1/M2."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core.stage import (
    EffectRequest,
    NeedEffects,
    ProjectList,
    StageContext,
    StageOutput,
    missing,
)


def _projects(inputs: Mapping[str, Any]) -> ProjectList:
    desc: ProjectList = inputs["projects.desc"]
    ga: ProjectList = inputs["projects.ga"]
    return ProjectList(projects=desc.projects + ga.projects)


def resolve(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    requests = tuple(
        EffectRequest(kind="overpass", params={"utility": utility}) for utility in ctx.run.utilities
    )
    need = missing(requests, effects)
    if need.requests:
        return need
    located = _projects(inputs)  # fixture projects already carry verified centers
    return StageOutput(value=located, counts={"projects": len(located.projects)}, fixture=True)


def fallback_town_gazetteer(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    located = _projects(inputs)
    return StageOutput(value=located, counts={"projects": len(located.projects)}, fixture=True)

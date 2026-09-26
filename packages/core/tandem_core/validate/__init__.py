"""Validation rules: one module per rule, registered here. Stub until M1."""

from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from tandem_core.stage import CheckList, NeedEffects, StageContext, StageOutput


def run_all(
    ctx: StageContext, inputs: Mapping[str, Any], effects: Mapping[str, JsonValue]
) -> StageOutput | NeedEffects:
    return StageOutput(value=CheckList(checks=()), counts={"checks": 0}, fixture=True)

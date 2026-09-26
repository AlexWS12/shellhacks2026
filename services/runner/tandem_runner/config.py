"""pipeline.yaml as typed, frozen config."""

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ConfigDict, Field, JsonValue

from tandem_core.models import Frozen
from tandem_core.stage import canonical_json


class Gate(Frozen):
    """Stage passes when counts[metric] equals counts[equals] (or the literal int)."""

    metric: str
    equals: str | int


class RunSection(Frozen):
    today: date
    distance_threshold_mi: float
    georgia_sponsors: tuple[str, ...]


class LlmSection(Frozen):
    model: str


class SourceSpec(Frozen):
    path: str
    utility: str | None = None
    in_service_field: str | None = None


class StageSpec(Frozen):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str
    agent: str | None = None
    fn: str
    effects: tuple[str, ...] = ()
    inputs: tuple[str, ...] = Field(default=(), alias="in")
    out: str | None = None
    timeout_s: float | None = Field(default=None, gt=0)
    fallback: tuple[str, ...] = ()
    gate: Gate | None = None
    top_n: int | None = None

    @property
    def params(self) -> dict[str, JsonValue]:
        """Stage-specific settings passed to the stage fn as ctx.params."""
        return {} if self.top_n is None else {"top_n": self.top_n}


class PipelineConfig(Frozen):
    run: RunSection
    utilities: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    llm: LlmSection
    sources: dict[str, SourceSpec]
    stages: tuple[StageSpec, ...]

    @property
    def config_hash(self) -> str:
        dumped = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(canonical_json(dumped).encode()).hexdigest()


def load_config(path: Path) -> PipelineConfig:
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PipelineConfig.model_validate(data)

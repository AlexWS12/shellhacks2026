from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from tandem_runner.cache import EffectCache
from tandem_runner.config import PipelineConfig, load_config
from tandem_runner.dag import Runner, import_dotted
from tandem_runner.effects import EXECUTORS, Executor
from tandem_runner.events import EventLog, open_db

ROOT = Path(__file__).resolve().parents[3]

MakeRunner = Callable[..., Runner]


@pytest.fixture
def config() -> PipelineConfig:
    return load_config(ROOT / "pipeline.yaml")


@pytest.fixture
def make_runner(tmp_path: Path) -> MakeRunner:
    """Build runners that share one SQLite file, so later runs see earlier ones."""
    db = open_db(tmp_path / "tandem.db")

    def make(
        config: PipelineConfig,
        *,
        overrides: Mapping[str, object] | None = None,
        executors: Mapping[str, Executor] = EXECUTORS,
    ) -> Runner:
        def resolve(path: str) -> object:
            if overrides and path in overrides:
                return overrides[path]
            return import_dotted(path)

        return Runner(
            config,
            EventLog(db),
            EffectCache(db),
            root=ROOT,
            llm_model="test-model",
            resolve=resolve,
            executors=executors,
        )

    return make


WithStage = Callable[..., PipelineConfig]


@pytest.fixture
def with_stage() -> WithStage:
    """Copy a config with one stage's fields updated."""

    def update_stage(config: PipelineConfig, stage_id: str, **update: object) -> PipelineConfig:
        stages = tuple(
            s.model_copy(update=update) if s.id == stage_id else s for s in config.stages
        )
        return config.model_copy(update={"stages": stages})

    return update_stage

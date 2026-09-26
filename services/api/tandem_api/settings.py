import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    config_path: Path  # pipeline.yaml; its directory is the repo root for source paths
    db_path: Path
    runs_dir: Path  # recorded runs (JSON Lines) imported on startup
    poll_interval_s: float = 0.1  # how often a live stream checks for new events
    heartbeat_s: float = 15.0  # idle time before a keep-alive comment
    replay_max_gap_s: float = 2.0
    sleep: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)

    @property
    def root(self) -> Path:
        return self.config_path.parent

    @property
    def sources_dir(self) -> Path:
        return self.root / "data" / "sources"

    @property
    def llm_model_override(self) -> str | None:
        return os.environ.get("GEMINI_MODEL") or None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            config_path=Path(os.environ.get("TANDEM_PIPELINE") or "pipeline.yaml").resolve(),
            db_path=Path(os.environ.get("TANDEM_DB") or "data/tandem.db").resolve(),
            runs_dir=Path(os.environ.get("TANDEM_RUNS_DIR") or "data/runs").resolve(),
        )

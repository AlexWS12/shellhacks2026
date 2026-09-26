from pathlib import Path
from typing import Any

import pytest
import yaml

from tandem_runner.config import PipelineConfig
from tandem_runner.dag import PipelineError, plan

ROOT = Path(__file__).resolve().parents[3]


def raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / "pipeline.yaml").read_text())
    return data


def stage(data: dict[str, Any], stage_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(s for s in data["stages"] if s["id"] == stage_id)
    return found


def invalid(data: dict[str, Any]) -> str:
    with pytest.raises(PipelineError) as exc:
        plan(PipelineConfig.model_validate(data))
    return str(exc.value)


def test_repo_pipeline_plans_in_declared_order() -> None:
    stages = plan(PipelineConfig.model_validate(raw()))
    assert [s.spec.id for s in stages] == [s["id"] for s in raw()["stages"]]
    locate = next(s for s in stages if s.spec.id == "locate")
    assert [name for name, _ in locate.fallbacks] == ["last_recorded", "town_gazetteer"]


def test_order_follows_dependencies_not_declaration() -> None:
    data = raw()
    data["stages"].reverse()
    order = [s.spec.id for s in plan(PipelineConfig.model_validate(data))]
    pairs = [("extract_desc", "locate"), ("locate", "overlap"), ("rank_and_cost", "briefs")]
    for before, after in pairs:
        assert order.index(before) < order.index(after)


def test_unknown_input() -> None:
    data = raw()
    stage(data, "overlap")["in"].append("projects.nowhere")
    assert "stage 'overlap': unknown input 'projects.nowhere'" in invalid(data)


def test_cycle() -> None:
    data = raw()
    stage(data, "extract_desc")["in"].append("overlaps")
    assert "cycle among stages" in invalid(data)


def test_missing_fn() -> None:
    data = raw()
    stage(data, "validate")["fn"] = "tandem_core.validate.does_not_exist"
    assert "stage 'validate': fn 'tandem_core.validate.does_not_exist' not found" in invalid(data)


def test_missing_module() -> None:
    data = raw()
    stage(data, "validate")["fn"] = "tandem_core.nope.run"
    assert "cannot import 'tandem_core.nope'" in invalid(data)


def test_missing_fallback_fn() -> None:
    data = raw()
    stage(data, "briefs")["fallback"] = ["carrier_pigeon"]
    assert "fallback 'carrier_pigeon'" in invalid(data)


def test_unknown_effect() -> None:
    data = raw()
    stage(data, "locate")["effects"].append("teleport")
    assert "no executor for effect 'teleport'" in invalid(data)


def test_duplicate_output_and_unknown_utility_reported_together() -> None:
    data = raw()
    stage(data, "validate")["out"] = "overlaps"
    data["pairs"].append(["DESC", "TVA"])
    message = invalid(data)
    assert "stage 'overlap': output 'overlaps' is also produced by validate" in message
    assert "unknown utility 'TVA'" in message


def test_unknown_stage_key_rejected() -> None:
    data = raw()
    stage(data, "overlap")["timeout"] = 5  # typo for timeout_s
    with pytest.raises(ValueError):
        PipelineConfig.model_validate(data)

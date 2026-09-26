"""Python half of the reducer parity test; apps/web/lib/reducer.test.ts is the other half.

Both fold the same event logs and compare against the same committed
packages/contracts/fixtures/reducer/<name>.state.json files.
"""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from tandem_core.models import Event
from tandem_core.reduce import fold

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages" / "contracts" / "fixtures" / "reducer"
EVENT: TypeAdapter[Event] = TypeAdapter(Event)

LOGS = {p.stem: p for p in sorted((ROOT / "data" / "runs").glob("*.jsonl"))}
LOGS["edge-cases"] = FIXTURES / "edge-cases.jsonl"


def test_every_recorded_run_has_a_fixture() -> None:
    expected = {f"{name}.state.json" for name in LOGS}
    assert expected == {p.name for p in FIXTURES.glob("*.state.json")}, "run `make types`"


@pytest.mark.parametrize("name", sorted(LOGS))
def test_fold_matches_shared_fixture(name: str) -> None:
    lines = LOGS[name].read_text(encoding="utf-8").splitlines()
    events = [EVENT.validate_json(line) for line in lines if line]
    expected = json.loads((FIXTURES / f"{name}.state.json").read_text(encoding="utf-8"))
    assert fold(events).model_dump(mode="json") == expected

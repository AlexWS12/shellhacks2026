import subprocess
import sys
from pathlib import Path

from tandem_core.schema import MODELS, json_schemas

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "export_schema.py"


def test_one_schema_per_model_plus_event() -> None:
    expected = {f"{m.__name__}.json" for m in MODELS} | {"Event.json"}
    assert set(json_schemas()) == expected


def test_export_is_deterministic(tmp_path: Path) -> None:
    runs = []
    for i in (1, 2):
        out = tmp_path / f"run{i}"
        subprocess.run([sys.executable, str(SCRIPT), "--out", str(out)], check=True)
        runs.append({p.name: p.read_bytes() for p in sorted(out.iterdir())})
    assert runs[0] == runs[1]
    assert len(runs[0]) == len(MODELS) + 1


def test_committed_schema_is_current() -> None:
    committed = ROOT / "packages" / "contracts" / "schema"
    on_disk = {p.name: p.read_text(encoding="utf-8") for p in committed.glob("*.json")}
    assert on_disk == json_schemas(), "schema is stale; run `make types`"

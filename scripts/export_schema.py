"""Write one JSON Schema per contract model, plus the Event union, to packages/contracts/schema/."""

import argparse
from pathlib import Path

from tandem_core.schema import json_schemas

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "packages" / "contracts" / "schema"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    out: Path = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    schemas = json_schemas()
    for stale in out.glob("*.json"):
        if stale.name not in schemas:
            stale.unlink()
    for name, text in schemas.items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(schemas)} schemas to {out}")


if __name__ == "__main__":
    main()

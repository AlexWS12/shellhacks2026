"""Record pipeline runs as JSON Lines event logs in data/runs/ (the demo fallback).

Each file holds one run: one Event per line, from run.started to run.completed.
The API imports these on startup so they can be listed and replayed offline.
"""

import argparse
import os
from pathlib import Path

from tandem_runner.cache import EffectCache
from tandem_runner.config import load_config
from tandem_runner.dag import Runner
from tandem_runner.events import EVENT, EventLog, open_db

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--prefix", default="stub")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "runs")
    parser.add_argument("--config", type=Path, default=ROOT / "pipeline.yaml")
    args = parser.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob(f"{args.prefix}-*.jsonl"):
        stale.unlink()

    config = load_config(args.config)
    db = open_db(":memory:")
    log = EventLog(db)
    runner = Runner(
        config,
        log,
        EffectCache(db),
        root=args.config.resolve().parent,
        llm_model=os.environ.get("GEMINI_MODEL") or config.llm.model,
    )
    for i in range(1, args.count + 1):
        result = runner.run()
        path = out / f"{args.prefix}-{i}.jsonl"
        lines = [EVENT.dump_json(e).decode() for e in log.events(result.run_id)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"recorded {result.status} run {result.run_id} -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""CLI: `python -m tandem_runner run` runs pipeline.yaml and prints events as JSON lines."""

import argparse
import os
import sys
from pathlib import Path

from tandem_core.models import Event
from tandem_runner.cache import EffectCache
from tandem_runner.config import load_config
from tandem_runner.dag import PipelineError, Runner
from tandem_runner.events import EVENT, EventLog, open_db


def _print_event(event: Event) -> None:
    sys.stdout.write(EVENT.dump_json(event).decode() + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tandem_runner")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run pipeline.yaml and print events as JSON lines")
    run.add_argument("--config", type=Path, default=Path("pipeline.yaml"))
    run.add_argument("--db", default=os.environ.get("TANDEM_DB") or "data/tandem.db")
    args = parser.parse_args(argv)

    config_path: Path = args.config.resolve()
    try:
        config = load_config(config_path)
        db = open_db(args.db)
        log = EventLog(db)
        log.subscribe(_print_event)
        runner = Runner(
            config,
            log,
            EffectCache(db),
            root=config_path.parent,
            llm_model=os.environ.get("GEMINI_MODEL") or config.llm.model,
        )
        result = runner.run()
    except PipelineError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())

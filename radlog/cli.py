"""CLI entrypoint for the RadMachine importer."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radlog")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--user")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.exists():
        print(
            f"Config file not found: {config_path}. Copy config.toml.example to config.toml.",
            file=sys.stderr,
        )
        return 2

    config = load_config(config_path)
    payload = {
        "start": args.start,
        "end": args.end,
        "user": args.user or config.radmachine.username,
        "config": asdict(config),
        "candidates": [],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

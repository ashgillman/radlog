"""CLI entrypoint for the RadMachine importer."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import requests

from .api import RadMachineClient
from .collect import collect_qa_sessions, serialize_source_records
from .config import ConfigError, load_config
from .group import group_source_records, serialize_candidate_entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radlog")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--user")
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument(
        "--endpoint",
        default="",
        help="Endpoint relative to /<customer_id>/api/. Empty means probe the API root.",
    )
    parser.add_argument(
        "--paginate",
        action="store_true",
        help="Follow DRF-style pagination and return collected results for the endpoint.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int)
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--collect", choices=("qa-sessions", "qa-candidates"))
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

    try:
        config = load_config(config_path)
        client = RadMachineClient(config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        params = _build_query_params(args, config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if args.collect == "qa-sessions":
            records = collect_qa_sessions(
                client,
                start=args.start,
                end=args.end,
                user=args.user or config.radmachine.username,
                extra_params=params,
            )
            server_payload = None
            collected_payload = serialize_source_records(records)
            candidate_payload = []
        elif args.collect == "qa-candidates":
            records = collect_qa_sessions(
                client,
                start=args.start,
                end=args.end,
                user=args.user or config.radmachine.username,
                extra_params=params,
            )
            server_payload = None
            collected_payload = serialize_source_records(records)
            candidate_payload = serialize_candidate_entries(group_source_records(records))
        else:
            server_payload = (
                list(client.paginate(args.endpoint, params=params))
                if args.paginate
                else client.get_json(args.endpoint, params=params)
            )
            collected_payload = None
            candidate_payload = []
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        print(f"RadMachine API request failed with HTTP {status}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"RadMachine API request failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "start": args.start,
        "end": args.end,
        "user": args.user or config.radmachine.username,
        "endpoint": args.endpoint or "/",
        "config": _redacted_config(config),
        "server": server_payload,
        "records": collected_payload,
        "candidates": candidate_payload,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_query_params(args: argparse.Namespace, config) -> dict[str, str]:
    params: dict[str, str] = {}
    if args.limit is not None:
        params["limit"] = str(args.limit)
    if args.offset is not None:
        params["offset"] = str(args.offset)
    for item in args.param:
        key, sep, value = item.partition("=")
        if not sep:
            raise ConfigError(f"Invalid --param value {item!r}; expected KEY=VALUE")
        params[key] = value
    return params


def _redacted_config(config) -> dict:
    data = asdict(config)
    data["radmachine"]["token_env"] = config.radmachine.token_env
    return data


if __name__ == "__main__":
    raise SystemExit(main())

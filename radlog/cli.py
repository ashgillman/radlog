"""CLI entrypoint for the RadMachine importer."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date as Date
from datetime import timedelta
from typing import Any

import requests

from .api import RadMachineClient
from .collect import collect_qa_sessions, collect_service_events, serialize_source_records
from .config import ConfigError, load_config, resolve_config_path
from .extensions import load_callable, load_object
from .group import group_source_records, serialize_candidate_entries
from .report_collect import collect_abnormal_qa_report
from .report_models import AbnormalQaReport, QaIssue, ReportCollectionProfile
from .rm_models import ApiObject


RAW_EXPORT_TARGETS = (
    "qa-testlistinstances",
    "qa-testinstances",
    "qa-unittestcollections",
    "units",
    "service-events",
    "service-log-return-to-service-qa",
)

RAW_EXPORT_DEFAULT_ORDERING = {
    "qa-testlistinstances": "-work_completed",
    "qa-testinstances": "-work_completed",
    "qa-unittestcollections": "due_date",
    "service-events": "-datetime_service",
    "service-log-return-to-service-qa": "-datetime_assigned",
}

REPORT_DEFAULT_DAYS = 7


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radlog")
    parser.add_argument("--config")
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
    parser.add_argument("--report", choices=("abnormal-qa",))
    parser.add_argument(
        "--filter-by-results",
        default="action,tolerance,comment",
        help="Comma-separated report issue filters: action, tolerance/tol, comment, all.",
    )
    parser.add_argument("--render", choices=("json", "plaintext"), default="json")
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Print report collection timing and request counters to stderr.",
    )
    parser.add_argument(
        "--export-raw",
        choices=RAW_EXPORT_TARGETS,
        help="Export raw payloads from a named typed endpoint without normalization or rendering.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.report and (args.collect or args.export_raw):
        print("--report cannot be combined with --collect or --export-raw", file=sys.stderr)
        return 2
    if args.export_raw and args.collect:
        print("--export-raw cannot be combined with --collect", file=sys.stderr)
        return 2

    try:
        params = _build_query_params(args)
        if args.export_raw:
            params = _build_raw_export_query_params(args, params)
        report_filters = _parse_report_filters(args.filter_by_results)
        start, end = _effective_dates(args)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    config_path = resolve_config_path(args.config)
    if not config_path.exists():
        print(
            f"Config file not found: {config_path}. Copy config.toml.example to that path or pass --config.",
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
        if args.collect == "qa-sessions":
            records = collect_qa_sessions(
                client,
                start=start,
                end=end,
                user=args.user or config.radmachine.username,
                extra_params=params,
            )
            server_payload = None
            collected_payload = serialize_source_records(records)
            candidate_payload = []
            raw_export_payload = None
            report_payload = None
        elif args.collect == "qa-candidates":
            records = collect_qa_sessions(
                client,
                start=start,
                end=end,
                user=args.user or config.radmachine.username,
                extra_params=params,
            ) + collect_service_events(
                client,
                start=start,
                end=end,
                extra_params={},
            )
            server_payload = None
            collected_payload = serialize_source_records(records)
            renderer = load_callable(
                config.render.logbook_org_renderer,
                search_paths=config.extensions.paths,
            )
            rules = load_object(
                config.grouping.rules,
                search_paths=config.extensions.paths,
            )
            candidates = group_source_records(records, rules=rules)
            for candidate in candidates:
                candidate.rendered_org = renderer(candidate)
            candidate_payload = serialize_candidate_entries(candidates)
            raw_export_payload = None
            report_payload = None
        elif args.export_raw:
            server_payload = None
            collected_payload = None
            candidate_payload = []
            raw_export_payload = _export_raw_payloads(
                client,
                args.export_raw,
                params=params,
                start=start,
                end=end,
            )
            report_payload = None
        elif args.report == "abnormal-qa":
            profile = ReportCollectionProfile() if args.profile else None
            report = collect_abnormal_qa_report(
                client,
                start=start or "",
                end=end or "",
                extra_params=params,
                profile=profile,
            )
            report.issues = [issue for issue in report.issues if issue.issue_type in report_filters]
            if profile is not None:
                _write_report_profile(profile)
            if args.render == "plaintext":
                sys.stdout.write(_render_abnormal_qa_plaintext(report))
                return 0
            server_payload = None
            collected_payload = None
            candidate_payload = []
            raw_export_payload = None
            report_payload = _serialize_report(report)
        else:
            server_payload = (
                list(client.paginate(args.endpoint, params=params))
                if args.paginate
                else client.get_json(args.endpoint, params=params)
            )
            collected_payload = None
            candidate_payload = []
            raw_export_payload = None
            report_payload = None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        print(f"RadMachine API request failed with HTTP {status}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"RadMachine API request failed: {exc}", file=sys.stderr)
        return 1

    payload = {
        "start": start,
        "end": end,
        "user": args.user or config.radmachine.username,
        "endpoint": args.endpoint or "/",
        "config": _redacted_config(config),
        "server": server_payload,
        "records": collected_payload,
        "candidates": candidate_payload,
        "raw_export": raw_export_payload,
        "report": report_payload,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_query_params(args: argparse.Namespace) -> dict[str, str]:
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


def _build_raw_export_query_params(args: argparse.Namespace, params: dict[str, str]) -> dict[str, str]:
    params = dict(params)
    if args.export_raw not in RAW_EXPORT_DEFAULT_ORDERING:
        if args.start or args.end:
            raise ConfigError(f"--start/--end are not supported for --export-raw {args.export_raw}")
        return params

    params.setdefault("ordering", RAW_EXPORT_DEFAULT_ORDERING[args.export_raw])
    return params


def _effective_dates(args: argparse.Namespace) -> tuple[str | None, str | None]:
    if args.report != "abnormal-qa":
        return args.start, args.end

    end = args.end or Date.today().isoformat()
    if args.start:
        return args.start, end

    try:
        end_date = Date.fromisoformat(end)
    except ValueError as exc:
        raise ConfigError(f"Invalid --end date {end!r}; expected YYYY-MM-DD") from exc
    start = (end_date - timedelta(days=REPORT_DEFAULT_DAYS)).isoformat()
    return start, end


def _parse_report_filters(value: str) -> set[str]:
    aliases = {
        "action": "action",
        "actions": "action",
        "fail": "action",
        "fails": "action",
        "failure": "action",
        "tol": "tolerance",
        "tolerance": "tolerance",
        "tolerances": "tolerance",
        "comment": "comment",
        "comments": "comment",
    }
    normalized: set[str] = set()
    for item in value.split(","):
        key = item.strip().lower()
        if not key:
            continue
        if key == "all":
            return {"action", "tolerance", "comment"}
        if key not in aliases:
            raise ConfigError(f"Unknown --filter-by-results value {item!r}")
        normalized.add(aliases[key])
    return normalized or {"action", "tolerance", "comment"}


def _export_raw_payloads(
    client: RadMachineClient,
    target: str,
    params: dict[str, str],
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    methods = {
        "qa-testlistinstances": client.qa_test_list_instances,
        "qa-testinstances": client.qa_test_instances,
        "qa-unittestcollections": client.qa_unit_test_collections,
        "units": client.units,
        "service-events": client.service_events,
        "service-log-return-to-service-qa": client.service_log_return_to_service_qa,
    }
    records = methods[target](params=params)
    return [_raw_payload(record) for record in records if _raw_export_record_in_range(target, record, start, end)]


def _raw_payload(record: ApiObject) -> dict[str, Any]:
    return record.raw


def _raw_export_record_in_range(target: str, record: ApiObject, start: str | None, end: str | None) -> bool:
    if not start and not end:
        return True

    date_value = _raw_export_record_date(target, record)
    if not date_value:
        return False
    date = date_value[:10]
    if start and date < start:
        return False
    if end and date > end:
        return False
    return True


def _raw_export_record_date(target: str, record: ApiObject) -> str | None:
    if target == "qa-testlistinstances":
        return getattr(record, "performed_at", None)
    if target == "qa-testinstances":
        return getattr(record, "work_completed", None)
    if target == "qa-unittestcollections":
        return getattr(record, "due_date", None)
    if target == "service-events":
        return getattr(record, "performed_at", None)
    if target == "service-log-return-to-service-qa":
        return getattr(record, "datetime_assigned", None)
    return None


def _serialize_report(report: AbnormalQaReport) -> dict[str, Any]:
    return asdict(report)


def _write_report_profile(profile: ReportCollectionProfile) -> None:
    print("Abnormal QA collection profile:", file=sys.stderr)
    print(f"  sessions_seen: {profile.sessions_seen}", file=sys.stderr)
    print(f"  sessions_in_range: {profile.sessions_in_range}", file=sys.stderr)
    print(f"  sessions_with_issues: {profile.sessions_with_issues}", file=sys.stderr)
    print(f"  metadata_fetches: {profile.metadata_fetches}", file=sys.stderr)
    for kind, count in sorted(profile.metadata_fetches_by_kind.items()):
        print(f"    {kind}: {count}", file=sys.stderr)
    print(f"  metadata_cache_hits: {profile.metadata_cache_hits}", file=sys.stderr)
    print(f"  test_lists_flattened: {profile.test_lists_flattened}", file=sys.stderr)
    print(f"  seconds_paginating: {profile.seconds_paginating:.3f}", file=sys.stderr)
    print(f"  seconds_metadata: {profile.seconds_metadata:.3f}", file=sys.stderr)
    print(f"  seconds_flattening: {profile.seconds_flattening:.3f}", file=sys.stderr)


def _render_abnormal_qa_plaintext(report: AbnormalQaReport) -> str:
    lines = [f"Abnormal QA Report: {report.start} to {report.end}"]
    grouped: dict[str, list[QaIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue.equipment_group or "Unknown equipment", []).append(issue)

    for equipment in sorted(grouped):
        lines.extend(["", equipment])
        lines.append("-" * len(equipment))
        for issue in grouped[equipment]:
            parts = [
                issue.performed_at[:10] if issue.performed_at else "unknown-date",
                issue.issue_type,
                issue.collection_name or "Unknown QA",
                issue.test_label or "Unknown test",
                f"value={issue.value!r}",
            ]
            if issue.session_url:
                parts.append(issue.session_url)
            lines.append(" | ".join(parts))
            if issue.comment:
                lines.append(f"  Comment: {issue.comment}")
    lines.append("")
    return "\n".join(lines)


def _redacted_config(config) -> dict:
    data = asdict(config)
    data["radmachine"]["token"] = "<redacted>" if config.radmachine.token else None
    data["radmachine"]["token_env"] = config.radmachine.token_env
    return data


if __name__ == "__main__":
    raise SystemExit(main())

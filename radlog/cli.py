"""CLI entrypoint for the RadMachine importer."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import webbrowser

import requests

from .api import RadMachineClient
from .collect import collect_qa_sessions, collect_service_events, serialize_source_records
from .config import Config, ConfigError, ReportPresetConfig, load_config, resolve_config_path
from .extensions import load_callable, load_object
from .group import group_source_records, serialize_candidate_entries
from .report_collect import collect_qa_report
from .report_filters import apply_issue_filters, exact_user_filter_value, issue_filter_for_types, parse_where
from .report_models import QaReport, QaIssue, ReportCollectionProfile
from .report_renderers.html import render_qa_html
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
RELATIVE_DATE_WINDOWS = {
    "day": 1,
    "week": 7,
    "month": 30,
}
REPORT_TYPES = {"qa"}


@dataclass(slots=True)
class ReportOptions:
    report_type: str
    start: str | None
    end: str | None
    render: str
    user: str | None
    issue_types: set[str]
    filters: list
    params: dict[str, str]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radlog")
    parser.add_argument("--config")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--last-day", action="store_true", help="Use the last day as the date range.")
    parser.add_argument("--last-week", action="store_true", help="Use the last seven days as the date range.")
    parser.add_argument("--last-month", action="store_true", help="Use the last thirty days as the date range.")
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
    parser.add_argument("--report")
    parser.add_argument(
        "--filter-by-results",
        default=None,
        help="Compatibility alias for --where 'issue in ...'. Values: action, tolerance/tol, comment, all.",
    )
    parser.add_argument(
        "--where",
        action="append",
        default=[],
        help="Find-style report filter expression. Repeat expressions are combined with implicit AND.",
    )
    parser.add_argument("--render", choices=("json", "plaintext", "html", "html-serve"), default=None)
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
        cli_where_filters = [parse_where(expression) for expression in args.where]
        cli_report_issue_types = _parse_report_filters(args.filter_by_results) if args.filter_by_results else None
        params = _build_query_params(args)
        if args.export_raw:
            params = _build_raw_export_query_params(args, params)
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
        report_options = _resolve_report_options(
            args,
            config,
            params=params,
            default_start=start,
            default_end=end,
            cli_where_filters=cli_where_filters,
            cli_report_issue_types=cli_report_issue_types,
        )
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
        elif report_options and report_options.report_type == "qa":
            profile = ReportCollectionProfile() if args.profile else None
            report = collect_qa_report(
                client,
                start=report_options.start or "",
                end=report_options.end or "",
                extra_params=report_options.params,
                profile=profile,
                include_normal_results=bool(report_options.issue_types & {"normal", "skipped"}),
            )
            report.issues = apply_issue_filters(report.issues, report_options.filters)
            if profile is not None:
                _write_report_profile(profile)
            if report_options.render == "plaintext":
                sys.stdout.write(_render_qa_plaintext(report))
                return 0
            if report_options.render == "html":
                sys.stdout.write(render_qa_html(report))
                return 0
            if report_options.render == "html-serve":
                _serve_html(render_qa_html(report))
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
        "start": report_options.start if report_options else start,
        "end": report_options.end if report_options else end,
        "user": report_options.user if report_options else args.user or config.radmachine.username,
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
    report_type = args.report if args.report in REPORT_TYPES else None
    return _effective_report_dates(report_type, args.start, args.end, _relative_date_window(args))


def _effective_report_dates(
    report_type: str | None,
    start: str | None,
    end: str | None,
    relative_window: str | None,
) -> tuple[str | None, str | None]:
    if relative_window:
        if start or end:
            raise ConfigError("--last-day/--last-week/--last-month cannot be combined with --start or --end")
        end_date = Date.today()
        start = (end_date - timedelta(days=RELATIVE_DATE_WINDOWS[relative_window])).isoformat()
        return start, end_date.isoformat()

    if report_type != "qa":
        return start, end

    end = end or Date.today().isoformat()
    if start:
        return start, end

    try:
        end_date = Date.fromisoformat(end)
    except ValueError as exc:
        raise ConfigError(f"Invalid --end date {end!r}; expected YYYY-MM-DD") from exc
    start = (end_date - timedelta(days=REPORT_DEFAULT_DAYS)).isoformat()
    return start, end


def _relative_date_window(args: argparse.Namespace) -> str | None:
    selected = [
        name
        for name, enabled in (
            ("day", args.last_day),
            ("week", args.last_week),
            ("month", args.last_month),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise ConfigError("--last-day, --last-week, and --last-month are mutually exclusive")
    return selected[0] if selected else None


def _resolve_report_options(
    args: argparse.Namespace,
    config: Config,
    *,
    params: dict[str, str],
    default_start: str | None,
    default_end: str | None,
    cli_where_filters,
    cli_report_issue_types: set[str] | None,
) -> ReportOptions | None:
    if not args.report:
        return None

    preset = _report_preset(args.report, config)
    report_type = preset.type if preset else args.report
    if report_type not in REPORT_TYPES:
        raise ConfigError(f"Unknown report type {report_type!r} for --report {args.report!r}")

    _reject_ambiguous_filter_overrides(args, preset)
    render = args.render or (preset.render if preset else None) or "json"
    if render not in {"json", "plaintext", "html", "html-serve"}:
        raise ConfigError(f"Unknown render value {render!r} in report preset {args.report!r}")

    start, end = _report_dates_from_args_or_preset(args, preset, report_type, default_start, default_end)
    issue_types = cli_report_issue_types or _parse_report_filters(preset.filter_by_results if preset else None)
    where_filters = cli_where_filters if not preset or not preset.where else [parse_where(expression) for expression in preset.where]
    filters = _build_report_filters(issue_types, where_filters)

    report_params = dict(params)
    if preset:
        report_params.update(preset.params)
    user = args.user or (preset.user if preset else None)
    report_params = _build_report_query_params(report_params, user, where_filters)

    return ReportOptions(
        report_type=report_type,
        start=start,
        end=end,
        render=render,
        user=user or config.radmachine.username,
        issue_types=issue_types,
        filters=filters,
        params=report_params,
    )


def _report_preset(report_name: str, config: Config) -> ReportPresetConfig | None:
    if report_name in REPORT_TYPES:
        return None
    preset = config.reports.get(report_name)
    if preset is None:
        raise ConfigError(f"Unknown report {report_name!r}; use a built-in report or define [reports.{report_name}]")
    return preset


def _reject_ambiguous_filter_overrides(args: argparse.Namespace, preset: ReportPresetConfig | None) -> None:
    if not preset:
        return
    preset_filters = bool(preset.user or preset.filter_by_results or preset.where or preset.params)
    cli_filters = bool(args.user or args.filter_by_results or args.where or args.param or args.limit is not None or args.offset is not None)
    if preset_filters and cli_filters:
        raise ConfigError(
            f"--report {args.report!r} defines filters; do not combine it with --user, --where, "
            "--filter-by-results, --param, --limit, or --offset"
        )


def _report_dates_from_args_or_preset(
    args: argparse.Namespace,
    preset: ReportPresetConfig | None,
    report_type: str,
    default_start: str | None,
    default_end: str | None,
) -> tuple[str | None, str | None]:
    if _cli_date_override_specified(args) or not preset:
        return default_start, default_end

    relative_window = preset.last
    if relative_window and relative_window not in RELATIVE_DATE_WINDOWS:
        raise ConfigError(f"Unknown last value {relative_window!r} in report preset {args.report!r}")
    return _effective_report_dates(report_type, preset.start, preset.end, relative_window)


def _cli_date_override_specified(args: argparse.Namespace) -> bool:
    return bool(args.start or args.end or args.last_day or args.last_week or args.last_month)


def _build_report_filters(report_issue_types: set[str], where_filters):
    filters = [issue_filter_for_types(report_issue_types)]
    filters.extend(where_filters)
    return filters


def _build_report_query_params(
    params: dict[str, str],
    user: str | None,
    where_filters,
) -> dict[str, str]:
    report_params = dict(params)
    user = user or next((value for expression in where_filters if (value := exact_user_filter_value(expression))), None)
    if user:
        _set_report_query_param(report_params, "created_by__username", user)
    return report_params


def _set_report_query_param(params: dict[str, str], key: str, value: str) -> None:
    existing = params.get(key)
    if existing is not None and existing != value:
        raise ConfigError(f"--param {key}={existing!r} conflicts with report filter {key}={value!r}")
    params[key] = value


def _parse_report_filters(value: str | None) -> set[str]:
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
        "normal": "normal",
        "normals": "normal",
        "ok": "normal",
        "skipped": "skipped",
        "skip": "skipped",
    }
    normalized: set[str] = set()
    for item in (value or "all").split(","):
        key = item.strip().lower()
        if not key:
            continue
        if key == "all":
            return {"action", "tolerance", "comment", "normal", "skipped"}
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


def _serialize_report(report: QaReport) -> dict[str, Any]:
    return asdict(report)


def _write_report_profile(profile: ReportCollectionProfile) -> None:
    print("QA report collection profile:", file=sys.stderr)
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


def _render_qa_plaintext(report: QaReport) -> str:
    lines = [f"QA Report: {report.start} to {report.end}"]
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


def _serve_html(html: str, *, host: str = "127.0.0.1", port: int = 0) -> None:
    with TemporaryDirectory(prefix="radlog-report-") as directory:
        path = Path(directory) / "index.html"
        path.write_text(html, encoding="utf-8")
        handler = partial(SimpleHTTPRequestHandler, directory=directory)
        with ThreadingHTTPServer((host, port), handler) as server:
            url = f"http://{host}:{server.server_address[1]}/"
            print(f"Serving report at {url}", file=sys.stderr)
            print("Press Ctrl-C to stop.", file=sys.stderr)
            webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                print("Stopped report server.", file=sys.stderr)


def _redacted_config(config) -> dict:
    data = asdict(config)
    data["radmachine"]["token"] = "<redacted>" if config.radmachine.token else None
    data["radmachine"]["token_env"] = config.radmachine.token_env
    return data


if __name__ == "__main__":
    raise SystemExit(main())

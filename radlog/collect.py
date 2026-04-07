"""Collection and normalization routines for RadMachine data."""

from __future__ import annotations

from dataclasses import asdict

from .api import RadMachineClient
from .models import SourceRecord


def collect_qa_sessions(
    client: RadMachineClient,
    *,
    start: str | None = None,
    end: str | None = None,
    user: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[SourceRecord]:
    params = dict(extra_params or {})
    params.setdefault("limit", "100")
    params.setdefault("ordering", "-work_completed")
    descending_by_completion = params.get("ordering") == "-work_completed"
    if user:
        params.setdefault("created_by__username", user)

    records: list[SourceRecord] = []
    cache: dict[str, dict] = {}

    for session in client.paginate("qa/testlistinstances", params=params):
        performed_at = session.get("work_completed") or session.get("work_started")
        if start and performed_at is not None and performed_at[:10] < start:
            if descending_by_completion:
                break
            continue
        if end and (performed_at is None or performed_at[:10] > end):
            continue

        collection_url = session.get("unit_test_collection")
        collection = _fetch_json(client, cache, collection_url)
        unit = _fetch_json(client, cache, collection.get("unit")) if collection else {}

        records.append(
            SourceRecord(
                source_type="qa_session",
                remote_id=_extract_id(session.get("url", "")),
                created_at=session.get("created"),
                updated_at=session.get("modified"),
                performed_at=performed_at,
                created_by=_extract_id(session.get("created_by", "")),
                unit=_split_unit_name(unit.get("name"))[0],
                site=_split_unit_name(unit.get("name"))[1],
                title=collection.get("name") or None,
                status=_session_status(session),
                raw={
                    "session": session,
                    "unit_test_collection": collection,
                    "unit": unit,
                },
            )
        )

    return records


def serialize_source_records(records: list[SourceRecord]) -> list[dict]:
    return [asdict(record) for record in records]


def _fetch_json(client: RadMachineClient, cache: dict[str, dict], url: str | None) -> dict:
    if not url:
        return {}
    if url not in cache:
        payload = client.get_json(url)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object payload from {url}")
        cache[url] = payload
    return cache[url]


def _extract_id(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else ""


def _split_unit_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    if " - " not in name:
        return name, None
    unit, site = name.split(" - ", 1)
    return unit, site


def _session_status(session: dict) -> str:
    if session.get("flagged"):
        return "flagged"
    if session.get("reviewed"):
        return "reviewed"
    return "completed"

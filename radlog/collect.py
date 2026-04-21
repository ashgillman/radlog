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


def collect_service_events(
    client: RadMachineClient,
    *,
    start: str | None = None,
    end: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[SourceRecord]:
    params = dict(extra_params or {})
    params.setdefault("limit", "100")
    params.setdefault("ordering", "-datetime_service")
    descending_by_service = params.get("ordering") == "-datetime_service"

    records: list[SourceRecord] = []
    cache: dict[str, dict] = {}
    selected_events: list[dict] = []

    for service_event in client.paginate("servicelog/serviceevents", params=params):
        performed_at = service_event.get("datetime_service") or service_event.get("datetime_created")
        if start and performed_at is not None and performed_at[:10] < start:
            if descending_by_service:
                break
            continue
        if end and (performed_at is None or performed_at[:10] > end):
            continue

        selected_events.append(service_event)

    return_to_service_qa = _collect_return_to_service_qa(
        client,
        cache,
        {
            service_event.get("url")
            for service_event in selected_events
            if service_event.get("url")
        },
    )

    for service_event in selected_events:
        unit_service_area = _fetch_json(client, cache, service_event.get("unit_service_area"))
        unit = _fetch_json(client, cache, unit_service_area.get("unit")) if unit_service_area else {}
        service_type = _fetch_json(client, cache, service_event.get("service_type"))
        service_status = _fetch_json(client, cache, service_event.get("service_status"))

        problem_description = str(service_event.get("problem_description", "")).strip()
        work_description = str(service_event.get("work_description", "")).strip()

        records.append(
            SourceRecord(
                source_type="service_event",
                remote_id=_extract_id(service_event.get("url", "")),
                created_at=service_event.get("datetime_created"),
                updated_at=service_event.get("datetime_modified"),
                performed_at=performed_at,
                created_by=_extract_id(service_event.get("user_created_by", "")),
                unit=unit.get("name") or None,
                title=problem_description or work_description or None,
                status=_service_event_status_name(service_status),
                raw={
                    "service_event": {
                        **service_event,
                        "event_url": _service_event_url(service_event.get("url")),
                        "return_to_service_qa": return_to_service_qa.get(service_event.get("url"), []),
                        "service_type_name": service_type.get("name"),
                        "service_status_name": service_status.get("name"),
                    },
                    "unit_service_area": unit_service_area,
                    "unit": unit,
                },
            )
        )

    return records


def serialize_source_records(records: list[SourceRecord]) -> list[dict]:
    return [asdict(record) for record in records]


def _collect_return_to_service_qa(
    client: RadMachineClient,
    cache: dict[str, dict],
    service_event_urls: set[str],
) -> dict[str, list[str]]:
    event_to_qa: dict[str, list[str]] = {}
    if not service_event_urls:
        return event_to_qa

    for item in client.paginate("servicelog/returntoserviceqa", params={"limit": "100"}):
        service_event_url = item.get("service_event")
        if service_event_url not in service_event_urls:
            continue
        unit_test_collection = _fetch_json(client, cache, item.get("unit_test_collection"))
        qa_name = str(unit_test_collection.get("name", "")).strip()
        if not service_event_url or not qa_name:
            continue
        event_to_qa.setdefault(service_event_url, []).append(qa_name)

    return event_to_qa


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


def _service_event_status_name(service_status: dict) -> str:
    name = str(service_status.get("name", "")).strip().lower()
    if not name:
        return "service_event"
    return name.replace(" ", "_")


def _service_event_url(api_url: str | None) -> str | None:
    if not api_url:
        return None
    service_event_id = _extract_id(api_url)
    marker = "/api/servicelog/serviceevents/"
    if marker not in api_url:
        return None
    prefix, _ = api_url.split(marker, 1)
    return f"{prefix}/servicelog/event/details/{service_event_id}/"

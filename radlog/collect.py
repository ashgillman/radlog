"""Collection and normalization routines for RadMachine data."""

from __future__ import annotations

from dataclasses import asdict

from .api import RadMachineClient
from .models import SourceRecord
from .rm_models import (
    ServiceEvent,
    ServiceLogReturnToServiceQA,
    Unit,
    UnitTestCollection,
    TestListInstance,
    extract_id,
)


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

    for session_payload in client.paginate("qa/testlistinstances", params=params):
        session = TestListInstance.from_api(session_payload)
        performed_at = session.performed_at
        if start and performed_at is not None and performed_at[:10] < start:
            if descending_by_completion:
                break
            continue
        if end and (performed_at is None or performed_at[:10] > end):
            continue

        collection_payload = _fetch_json(client, cache, session.unit_test_collection)
        collection = UnitTestCollection.from_api(collection_payload)
        unit_payload = _fetch_json(client, cache, collection.unit) if collection.unit else {}
        unit = Unit.from_api(unit_payload)
        unit_name, site = unit.short_name_and_site

        records.append(
            SourceRecord(
                source_type="qa_session",
                remote_id=session.remote_id,
                created_at=session.created,
                updated_at=session.modified,
                performed_at=performed_at,
                created_by=extract_id(session.created_by),
                unit=unit_name,
                site=site,
                title=collection.name,
                status=session.status,
                raw={
                    "session": session.raw,
                    "unit_test_collection": collection.raw,
                    "unit": unit.raw,
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
    selected_events: list[ServiceEvent] = []

    for service_event_payload in client.paginate("servicelog/serviceevents", params=params):
        service_event = ServiceEvent.from_api(service_event_payload)
        performed_at = service_event.performed_at
        if start and performed_at is not None and performed_at[:10] < start:
            if descending_by_service:
                break
            continue
        if end and (performed_at is None or performed_at[:10] > end):
            continue

        selected_events.append(service_event)

    for service_event in selected_events:
        unit_service_area = _fetch_json(client, cache, service_event.unit_service_area)
        unit = Unit.from_api(_fetch_json(client, cache, unit_service_area.get("unit")) if unit_service_area else {})
        service_type = _fetch_json(client, cache, service_event.service_type)
        service_status = _fetch_json(client, cache, service_event.service_status)

        problem_description = str(service_event.problem_description or "").strip()
        work_description = str(service_event.work_description or "").strip()

        records.append(
            SourceRecord(
                source_type="service_event",
                remote_id=service_event.remote_id,
                created_at=service_event.datetime_created,
                updated_at=service_event.datetime_modified,
                performed_at=service_event.performed_at,
                created_by=extract_id(service_event.user_created_by),
                unit=unit.name,
                title=problem_description or work_description or None,
                status=_service_event_status_name(service_status),
                raw={
                    "service_event": {
                        **service_event.raw,
                        "event_url": _service_event_url(service_event.url),
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


def collect_service_log_return_to_service_qa(
    client: RadMachineClient,
    *,
    service_event_urls: set[str] | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[ServiceLogReturnToServiceQA]:
    params = dict(extra_params or {})
    params.setdefault("limit", "100")

    records: list[ServiceLogReturnToServiceQA] = []
    for payload in client.paginate("servicelog/returntoserviceqa", params=params):
        record = ServiceLogReturnToServiceQA.from_api(payload)
        if service_event_urls is not None and record.service_event not in service_event_urls:
            continue
        records.append(record)
    return records


def _fetch_json(client: RadMachineClient, cache: dict[str, dict], url: str | None) -> dict:
    if not url:
        return {}
    if url not in cache:
        payload = client.get_json(url)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object payload from {url}")
        cache[url] = payload
    return cache[url]


def _service_event_status_name(service_status: dict) -> str:
    name = str(service_status.get("name", "")).strip().lower()
    if not name:
        return "service_event"
    return name.replace(" ", "_")


def _service_event_url(api_url: str | None) -> str | None:
    if not api_url:
        return None
    service_event_id = extract_id(api_url)
    marker = "/api/servicelog/serviceevents/"
    if marker not in api_url:
        return None
    prefix, _ = api_url.split(marker, 1)
    return f"{prefix}/servicelog/event/details/{service_event_id}/"

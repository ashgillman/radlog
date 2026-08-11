"""Collection and normalization routines for RadMachine data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

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


@dataclass(slots=True)
class ResolvedQaSession:
    session: TestListInstance
    collection: UnitTestCollection
    unit: Unit

    @property
    def session_id(self) -> str:
        return self.session.remote_id

    @property
    def collection_name(self) -> str:
        return self.collection.name or ""

    @property
    def unit_name(self) -> str:
        return self.unit.name or ""

    @property
    def short_unit_name(self) -> str | None:
        unit_name, _site = self.unit.short_name_and_site
        return unit_name


def collect_units(
    client: RadMachineClient,
    *,
    unit: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[Unit]:
    """Collect unit records, optionally matching full or short unit name."""
    params = dict(extra_params or {})
    params.setdefault("limit", "100")

    records: list[Unit] = []
    for payload in client.paginate("units/units", params=params):
        record = Unit.from_api(payload)
        if unit and unit not in {record.name, record.short_name_and_site[0]}:
            continue
        records.append(record)
    return records


def collect_unit_test_collections(
    client: RadMachineClient,
    *,
    unit: str | None = None,
    collection_name_matches: Callable[[str], bool] | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[UnitTestCollection]:
    """Collect unit/test-list assignments with optional unit and name filters."""
    params = dict(extra_params or {})
    params.setdefault("limit", "100")

    unit_names = _collection_filter_unit_names(client, unit)
    collections: list[UnitTestCollection] = []
    for unit_name in unit_names:
        query = dict(params)
        if unit_name:
            query.setdefault("unit__name", unit_name)
        for payload in client.paginate("qa/unittestcollections", params=query):
            collection = UnitTestCollection.from_api(payload)
            if collection_name_matches and not collection_name_matches(collection.name or ""):
                continue
            collections.append(collection)
    return collections


def collect_resolved_qa_sessions_for_collections(
    client: RadMachineClient,
    collections: list[UnitTestCollection],
    *,
    start: str | None = None,
    end: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[ResolvedQaSession]:
    """Collect performed QA sessions for already-selected assignments."""
    params = dict(extra_params or {})
    params.setdefault("limit", "100")
    params.setdefault("ordering", "-work_completed")
    descending_by_completion = params.get("ordering") == "-work_completed"

    sessions: list[ResolvedQaSession] = []
    cache: dict[str, dict] = {}
    for collection in collections:
        query = dict(params)
        query.setdefault("unit_test_collection", collection.remote_id)
        unit_record = Unit.from_api(_fetch_json(client, cache, collection.unit) if collection.unit else {})
        for session_payload in client.paginate("qa/testlistinstances", params=query):
            session = TestListInstance.from_api(session_payload)
            performed_at = session.performed_at
            if start and performed_at is not None and performed_at[:10] < start:
                if descending_by_completion:
                    break
                continue
            if end and (performed_at is None or performed_at[:10] > end):
                continue
            sessions.append(ResolvedQaSession(session=session, collection=collection, unit=unit_record))
    return sessions


def _collection_filter_unit_names(client: RadMachineClient, unit: str | None) -> list[str | None]:
    if not unit:
        return [None]
    if " - " in unit:
        return [unit]
    return [record.name for record in collect_units(client, unit=unit) if record.name]


def collect_resolved_qa_sessions(
    client: RadMachineClient,
    *,
    start: str | None = None,
    end: str | None = None,
    user: str | None = None,
    unit: str | None = None,
    collection_name_matches: Callable[[str], bool] | None = None,
    extra_params: dict[str, str] | None = None,
) -> list[ResolvedQaSession]:
    """Collect QA sessions with assignment and unit metadata.

    This is the reusable efficient path for workflows that need performed QA
    sessions rather than normalized logbook records.
    """
    params = dict(extra_params or {})
    params.setdefault("limit", "100")
    params.setdefault("ordering", "-work_completed")
    descending_by_completion = params.get("ordering") == "-work_completed"
    if user:
        params.setdefault("created_by__username", user)

    sessions: list[ResolvedQaSession] = []
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

        collection = UnitTestCollection.from_api(_fetch_json(client, cache, session.unit_test_collection))
        if collection_name_matches and not collection_name_matches(collection.name or ""):
            continue

        unit_record = Unit.from_api(_fetch_json(client, cache, collection.unit) if collection.unit else {})
        if unit and unit not in {unit_record.name, unit_record.short_name_and_site[0]}:
            continue
        sessions.append(ResolvedQaSession(session=session, collection=collection, unit=unit_record))

    return sessions


def resolve_qa_session(client: RadMachineClient, session_id: int | str) -> ResolvedQaSession:
    """Fetch one QA session with its assignment and unit metadata."""
    session_payload = client.get_json(f"qa/testlistinstances/{session_id}/")
    if not isinstance(session_payload, dict):
        raise ValueError(f"Expected session object for {session_id}")
    session = TestListInstance.from_api(session_payload)
    cache: dict[str, dict] = {}
    collection = UnitTestCollection.from_api(_fetch_json(client, cache, session.unit_test_collection))
    unit = Unit.from_api(_fetch_json(client, cache, collection.unit) if collection.unit else {})
    return ResolvedQaSession(session=session, collection=collection, unit=unit)


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

    return_to_service_by_event = _collect_return_to_service_by_event(
        client,
        selected_events,
        cache,
    )

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
                        "return_to_service": return_to_service_by_event.get(service_event.url, []),
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


def _collect_return_to_service_by_event(
    client: RadMachineClient,
    service_events: list[ServiceEvent],
    cache: dict[str, dict],
) -> dict[str, list[dict[str, object]]]:
    event_urls = {event.url for event in service_events if event.url}
    if not event_urls:
        return {}

    sessions_by_event: dict[str, dict[str, dict[str, object]]] = {}
    relations = collect_service_log_return_to_service_qa(
        client,
        service_event_urls=event_urls,
    )
    for relation in relations:
        if not relation.service_event or not relation.test_list_instance:
            continue
        session_url = _qa_review_url(relation.test_list_instance)
        if not session_url:
            continue
        collection = _fetch_json(client, cache, relation.unit_test_collection)
        group_name = str(collection.get("name", "")).strip()
        event_sessions = sessions_by_event.setdefault(relation.service_event, {})
        session = event_sessions.setdefault(
            session_url,
            {
                "label": "Return to Service QA",
                "session_url": session_url,
                "qa_groups": [],
            },
        )
        groups = session["qa_groups"]
        if isinstance(groups, list) and group_name and group_name not in groups:
            groups.append(group_name)

    result: dict[str, list[dict[str, object]]] = {}
    for event_url, sessions in sessions_by_event.items():
        values = list(sessions.values())
        for session in values:
            groups = session.get("qa_groups", [])
            if isinstance(groups, list):
                session["label"] = _return_to_service_label(groups)
        result[event_url] = values
    return result


def _return_to_service_label(groups: list[str]) -> str:
    prefixes = [group.split("::", 1)[0].strip() for group in groups if group.strip()]
    if prefixes and len(set(prefixes)) == 1:
        prefix = prefixes[0]
        if prefix.lower().endswith((" qa", " qc")):
            return prefix
        return f"{prefix} QA"
    return "Return to Service QA"


def _qa_review_url(api_url: str | None) -> str | None:
    if not api_url:
        return None
    marker = "/api/qa/testlistinstances/"
    if marker not in api_url:
        return None
    prefix, _ = api_url.split(marker, 1)
    return f"{prefix}/qa/session/review/{extract_id(api_url)}/"

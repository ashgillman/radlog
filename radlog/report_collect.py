"""Collection routines for factual QA reports."""

from __future__ import annotations

from time import perf_counter

import requests

from .api import RadMachineClient
from .report_models import AbnormalQaReport, QaIssue, ReportCollectionProfile, TestDefinition
from .rm_models import TestListInstance, Unit, UnitTestCollection, extract_id, split_unit_name


ABNORMAL_PASS_FAIL_VALUES = {
    "action": "action",
    "fail": "action",
    "failed": "action",
    "warning": "tolerance",
    "near_tol": "tolerance",
    "near_tolerance": "tolerance",
    "tol": "tolerance",
    "tolerance": "tolerance",
}


def collect_abnormal_qa_report(
    client: RadMachineClient,
    *,
    start: str,
    end: str,
    extra_params: dict[str, str] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> AbnormalQaReport:
    params = dict(extra_params or {})
    params.setdefault("limit", "100")
    params.setdefault("ordering", "-work_completed")
    descending_by_completion = params.get("ordering") == "-work_completed"

    report = AbnormalQaReport(start=start, end=end)
    cache: dict[str, dict] = {}
    test_definition_cache: dict[str, dict[int, TestDefinition]] = {}
    searched_test_orders: dict[str, set[int]] = {}

    payloads = client.paginate("qa/testlistinstances", params=params)
    while True:
        started = perf_counter()
        try:
            payload = next(payloads)
        except StopIteration:
            break
        if profile is not None:
            profile.seconds_paginating += perf_counter() - started
            profile.sessions_seen += 1
        session = TestListInstance.from_api(payload)
        performed_at = session.performed_at
        if start and performed_at is not None and performed_at[:10] < start:
            if descending_by_completion:
                break
            continue
        if end and (performed_at is None or performed_at[:10] > end):
            continue
        if profile is not None:
            profile.sessions_in_range += 1

        issue_instances = [
            (test_instance, issue_type)
            for test_instance in session.test_instances
            if (issue_type := _issue_type(test_instance)) is not None
        ]
        session_comments = [(comment, text) for comment in session.comments if (text := _comment(comment))]
        if not issue_instances and not session_comments:
            continue
        if profile is not None:
            profile.sessions_with_issues += 1

        collection_payload = _fetch_json(client, cache, session.unit_test_collection, profile=profile)
        collection = UnitTestCollection.from_api(collection_payload)
        unit_payload = _fetch_json(client, cache, collection.unit, profile=profile)
        unit = Unit.from_api(unit_payload)
        if issue_instances:
            test_list_key = session.test_list or ""
            needed_orders = {
                order for test_instance, _issue_type_name in issue_instances if isinstance((order := test_instance.get("order")), int)
            }
            definitions_by_order = test_definition_cache.setdefault(test_list_key, {})
            searched_orders = searched_test_orders.setdefault(test_list_key, set())
            missing_orders = needed_orders - searched_orders
            if missing_orders:
                definitions_by_order.update(
                    test_definitions_for_orders(
                        client,
                        test_list_key,
                        missing_orders,
                        cache=cache,
                        profile=profile,
                    )
                )
                searched_orders.update(missing_orders)
        else:
            definitions_by_order = {}

        for test_instance, issue_type in issue_instances:
            test_definition = _definition_for_order(definitions_by_order, test_instance.get("order"))
            report.issues.append(
                QaIssue(
                    session_id=session.remote_id,
                    session_url=session.site_url,
                    performed_at=performed_at,
                    equipment_name=unit.name,
                    equipment_group=_equipment_group(unit),
                    collection_name=collection.name,
                    test_label=test_definition.label if test_definition else None,
                    issue_type=issue_type,
                    severity=_severity(test_instance),
                    value=test_instance.get("value"),
                    pass_fail=test_instance.get("pass_fail"),
                    comment=_comment(test_instance),
                    commenter=_commenter(client, cache, test_instance, profile=profile),
                    raw=test_instance,
                )
            )
        for comment, text in session_comments:
            report.issues.append(
                QaIssue(
                    session_id=session.remote_id,
                    session_url=session.site_url,
                    performed_at=performed_at,
                    equipment_name=unit.name,
                    equipment_group=_equipment_group(unit),
                    collection_name=collection.name,
                    test_label="Session comment",
                    issue_type="comment",
                    severity=None,
                    value=None,
                    pass_fail=None,
                    comment=text,
                    commenter=_commenter(client, cache, comment, profile=profile),
                    raw=comment,
                )
            )

    return report


def test_definitions_for_orders(
    client: RadMachineClient,
    endpoint: str,
    orders: set[int],
    *,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> dict[int, TestDefinition]:
    cache = cache if cache is not None else {}
    started = perf_counter()

    definitions = _test_definitions_for_orders_from_details(
        client,
        endpoint,
        orders,
        cache=cache,
        profile=profile,
    )
    missing_orders = orders - set(definitions)
    if missing_orders:
        _next_order, fallback_definitions = _test_definitions_for_orders(
            client,
            endpoint,
            missing_orders,
            cache=cache,
            profile=profile,
            start_order=0,
        )
        definitions.update(fallback_definitions)

    if profile is not None:
        profile.seconds_flattening += perf_counter() - started
    return definitions


def _test_definitions_for_orders_from_details(
    client: RadMachineClient,
    endpoint: str,
    orders: set[int],
    *,
    cache: dict[str, dict],
    profile: ReportCollectionProfile | None,
) -> dict[int, TestDefinition]:
    details_endpoint = _test_list_details_endpoint(endpoint)
    if details_endpoint is None:
        return {}
    try:
        payload = _fetch_json(client, cache, details_endpoint, profile=profile)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return {}
        raise
    if profile is not None:
        profile.test_lists_flattened += _count_test_list_detail_nodes(payload)
    _next_order, definitions = _test_definitions_for_orders_from_detail_payload(payload, orders, start_order=0)
    return definitions


def _test_definitions_for_orders_from_detail_payload(
    payload: dict,
    orders: set[int],
    *,
    start_order: int,
) -> tuple[int, dict[int, TestDefinition]]:
    definitions: dict[int, TestDefinition] = {}
    current_order = start_order
    for test_payload in payload.get("tests", []) or []:
        if not isinstance(test_payload, dict):
            return start_order, {}
        if current_order in orders:
            definitions[current_order] = _test_definition_from_payload(test_payload)
        current_order += 1
    for child_payload in payload.get("test_lists", []) or []:
        if not isinstance(child_payload, dict):
            return start_order, {}
        current_order, child_definitions = _test_definitions_for_orders_from_detail_payload(
            child_payload,
            orders,
            start_order=current_order,
        )
        definitions.update(child_definitions)
    return current_order, definitions


def _test_definitions_for_orders(
    client: RadMachineClient,
    endpoint: str,
    orders: set[int],
    *,
    cache: dict[str, dict],
    profile: ReportCollectionProfile | None,
    start_order: int,
) -> tuple[int, dict[int, TestDefinition]]:
    if profile is not None:
        profile.test_lists_flattened += 1
    payload = _fetch_json(client, cache, endpoint, profile=profile)
    definitions: dict[int, TestDefinition] = {}
    current_order = start_order
    for test_endpoint in payload.get("tests", []) or []:
        if current_order in orders:
            test_payload = _fetch_json(client, cache, test_endpoint, profile=profile)
            definitions[current_order] = _test_definition_from_payload(test_payload)
        current_order += 1
    for child_endpoint in payload.get("test_lists", []) or []:
        current_order, child_definitions = _test_definitions_for_orders(
            client,
            child_endpoint,
            orders,
            cache=cache,
            profile=profile,
            start_order=current_order,
        )
        definitions.update(child_definitions)
    return current_order, definitions


def flatten_test_list(
    client: RadMachineClient,
    endpoint: str,
    *,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> list[TestDefinition]:
    cache = cache if cache is not None else {}
    started = perf_counter()
    definitions = _flatten_test_list(client, endpoint, cache=cache, profile=profile)
    if profile is not None:
        profile.seconds_flattening += perf_counter() - started
    return definitions


def _flatten_test_list(
    client: RadMachineClient,
    endpoint: str,
    *,
    cache: dict[str, dict],
    profile: ReportCollectionProfile | None = None,
) -> list[TestDefinition]:
    if profile is not None:
        profile.test_lists_flattened += 1
    payload = _fetch_json(client, cache, endpoint, profile=profile)
    definitions: list[TestDefinition] = []
    for test_endpoint in payload.get("tests", []) or []:
        test_payload = _fetch_json(client, cache, test_endpoint, profile=profile)
        definitions.append(_test_definition_from_payload(test_payload))
    for child_endpoint in payload.get("test_lists", []) or []:
        definitions.extend(_flatten_test_list(client, child_endpoint, cache=cache, profile=profile))
    return definitions


def _test_definition_from_payload(payload: dict) -> TestDefinition:
    return TestDefinition(
        label=str(payload.get("name") or ""),
        slug=str(payload.get("slug") or "") or None,
        url=str(payload.get("url") or "") or None,
        raw=payload,
    )


def _test_list_details_endpoint(endpoint: str) -> str | None:
    test_list_id = extract_id(endpoint)
    if not test_list_id:
        return None
    return f"qa/testlists-details/{test_list_id}/"


def _count_test_list_detail_nodes(payload: dict) -> int:
    count = 1
    for child_payload in payload.get("test_lists", []) or []:
        if isinstance(child_payload, dict):
            count += _count_test_list_detail_nodes(child_payload)
    return count


def _fetch_json(
    client: RadMachineClient,
    cache: dict[str, dict],
    endpoint: str | None,
    *,
    profile: ReportCollectionProfile | None = None,
) -> dict:
    if not endpoint:
        return {}
    if endpoint in cache:
        if profile is not None:
            profile.metadata_cache_hits += 1
        return cache[endpoint]

    started = perf_counter()
    payload = client.get_json(endpoint)
    if profile is not None:
        profile.metadata_fetches += 1
        kind = _metadata_kind(endpoint)
        profile.metadata_fetches_by_kind[kind] = profile.metadata_fetches_by_kind.get(kind, 0) + 1
        profile.seconds_metadata += perf_counter() - started
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload from {endpoint}")
    cache[endpoint] = payload
    return cache[endpoint]


def _metadata_kind(endpoint: str) -> str:
    cleaned = endpoint.split("?", 1)[0].rstrip("/")
    parts = cleaned.split("/")
    if len(parts) >= 2 and parts[-2].isdigit():
        parts = parts[:-1]
    if "api" in parts:
        parts = parts[parts.index("api") + 1 :]
    if len(parts) >= 2 and parts[-1].isdigit():
        parts = parts[:-1]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else "unknown"


def _issue_type(test_instance: dict) -> str | None:
    if test_instance.get("skipped"):
        return None
    pass_fail = test_instance.get("pass_fail")
    if isinstance(pass_fail, str):
        normalized = pass_fail.strip().lower()
        if normalized in ABNORMAL_PASS_FAIL_VALUES:
            return ABNORMAL_PASS_FAIL_VALUES[normalized]
    if _comment(test_instance):
        return "comment"
    return None


def _severity(test_instance: dict) -> str | None:
    pass_fail = test_instance.get("pass_fail")
    if isinstance(pass_fail, str):
        return pass_fail
    if pass_fail is not None:
        return str(pass_fail)
    return None


def _comment(test_instance: dict) -> str | None:
    text = str(test_instance.get("comment") or "").strip()
    return text or None


def _commenter(
    client: RadMachineClient,
    cache: dict[str, dict],
    payload: dict,
    *,
    profile: ReportCollectionProfile | None = None,
) -> str | None:
    user = payload.get("user") or payload.get("created_by") or payload.get("author")
    if isinstance(user, dict):
        return _username_from_payload(user)
    if not user:
        return None

    endpoint = str(user)
    if "/" not in endpoint:
        return endpoint
    user_payload = _fetch_json(client, cache, endpoint, profile=profile)
    return _username_from_payload(user_payload) or extract_id(endpoint)


def _username_from_payload(payload: dict) -> str | None:
    for key in ("username", "name", "email"):
        value = payload.get(key)
        if value:
            return str(value)
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or None


def _definition_for_order(definitions: dict[int, TestDefinition], order: object) -> TestDefinition | None:
    if not isinstance(order, int):
        return None
    return definitions.get(order)


def _equipment_group(unit: Unit) -> str | None:
    unit_name, site = split_unit_name(unit.name)
    return unit_name or site or unit.name

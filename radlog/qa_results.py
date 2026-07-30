"""Helpers for reading performed QA result rows."""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter
from typing import Any

import requests

from .api import RadMachineClient
from .report_models import ReportCollectionProfile, TestDefinition
from .rm_models import TestListInstance, extract_id


def test_result_by_slug(
    session: TestListInstance,
    slug: str,
    *,
    client: RadMachineClient | None = None,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> dict[str, Any] | None:
    """Return a performed test result from SESSION by test definition slug."""
    if client is not None:
        attach_test_result_slugs(client, [session], cache=cache, profile=profile)
    normalized_slug = _normalize_slug(slug)
    for test_result in session.test_instances:
        if _test_result_slug(session, test_result) == normalized_slug:
            return test_result
    return None


def numeric_test_value_by_slug(
    session: TestListInstance,
    slug: str,
    *,
    client: RadMachineClient | None = None,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> float | None:
    """Return a numeric performed test value from SESSION by test definition slug."""
    test_result = test_result_by_slug(session, slug, client=client, cache=cache, profile=profile)
    if test_result is None or test_result.get("skipped"):
        return None
    value = test_result.get("value")
    if value is None:
        return None
    return float(value)


def attach_test_result_slugs(
    client: RadMachineClient,
    sessions: Iterable[TestListInstance],
    *,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> None:
    """Annotate sessions with `order -> test slug` metadata for later lookup."""
    cache = cache if cache is not None else {}
    for session in sessions:
        orders = {order for item in session.test_instances if isinstance((order := item.get("order")), int)}
        if not orders or not session.test_list:
            continue
        definitions = test_definitions_for_orders(client, session.test_list, orders, cache=cache, profile=profile)
        session.raw["_radlog_test_slugs_by_order"] = {
            order: definition.slug for order, definition in definitions.items() if definition.slug
        }


def test_results_with_definitions(
    client: RadMachineClient,
    session: TestListInstance,
    *,
    cache: dict[str, dict] | None = None,
    profile: ReportCollectionProfile | None = None,
) -> list[tuple[dict[str, Any], TestDefinition | None]]:
    """Pair embedded session result rows with their test definitions when possible."""
    definitions = test_definitions_for_orders(
        client,
        session.test_list or "",
        {order for item in session.test_instances if isinstance((order := item.get("order")), int)},
        cache=cache,
        profile=profile,
    )
    return [
        (test_result, definitions.get(order) if isinstance((order := test_result.get("order")), int) else None)
        for test_result in session.test_instances
    ]


def _test_result_slug(session: TestListInstance, test_result: dict[str, Any]) -> str | None:
    for key in ("slug", "test_slug", "test__slug"):
        value = str(test_result.get(key) or "").strip()
        if value:
            return _normalize_slug(value)

    nested_test = test_result.get("test")
    if isinstance(nested_test, dict):
        value = str(nested_test.get("slug") or "").strip()
        if value:
            return _normalize_slug(value)

    order = test_result.get("order")
    slugs_by_order = session.raw.get("_radlog_test_slugs_by_order", {})
    if isinstance(order, int) and isinstance(slugs_by_order, dict):
        value = str(slugs_by_order.get(order) or "").strip()
        if value:
            return _normalize_slug(value)

    return None


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
        profile.seconds_metadata += perf_counter() - started
        profile.metadata_fetches += 1
        _count_metadata_fetch(endpoint, profile)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object payload from {endpoint}")
    cache[endpoint] = payload
    return payload


def _count_metadata_fetch(endpoint: str, profile: ReportCollectionProfile) -> None:
    if "qa/testlists-details/" in endpoint:
        kind = "qa/testlists-details"
    elif "qa/unittestcollections/" in endpoint:
        kind = "qa/unittestcollections"
    elif "units/units/" in endpoint:
        kind = "units/units"
    elif "auth/users/" in endpoint:
        kind = "auth/users"
    else:
        kind = "other"
    profile.metadata_fetches_by_kind[kind] = profile.metadata_fetches_by_kind.get(kind, 0) + 1


def _normalize_slug(value: str) -> str:
    return value.strip().lower()

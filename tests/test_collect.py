from __future__ import annotations

from radlog.collect import (
    collect_qa_sessions,
    collect_resolved_qa_sessions,
    collect_resolved_qa_sessions_for_collections,
    collect_service_events,
    collect_service_log_return_to_service_qa,
    collect_unit_test_collections,
)
from tests.support import TEST_BASE_URL, TEST_CUSTOMER_ID


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/13162/",
            "site_url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/qa/session/details/13162/",
            "created": "2026-03-06T10:10:59+10:00",
            "modified": "2026-03-06T10:10:59+10:00",
            "work_started": "2026-03-06T10:06:00+10:00",
            "work_completed": "2026-03-06T10:10:58+10:00",
            "flagged": False,
            "reviewed": "2026-03-09T11:14:03+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
            "created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
        }

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/206/"):
            return {
                "name": "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
        if endpoint.endswith("/2/"):
            return {"name": "LAx - LinacName"}
        raise AssertionError(endpoint)


def test_collect_qa_sessions_normalizes_session_records() -> None:
    client = FakeClient()

    records = collect_qa_sessions(
        client,
        start="2026-03-01",
        end="2026-03-31",
        user="example-user",
        extra_params={"limit": "5"},
    )

    assert len(records) == 1
    record = records[0]
    assert record.source_type == "qa_session"
    assert record.remote_id == "13162"
    assert record.performed_at == "2026-03-06T10:10:58+10:00"
    assert record.created_by == "27"
    assert record.title == "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV"
    assert record.unit == "LAx"
    assert record.site == "LinacName"
    assert record.status == "reviewed"
    assert record.raw["session"]["site_url"] == f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/qa/session/details/13162/"
    assert client.calls[0] == (
        "qa/testlistinstances",
        {"limit": "5", "ordering": "-work_completed", "created_by__username": "example-user"},
    )


class DefaultLimitClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        return iter(())

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        raise AssertionError(endpoint)


def test_collect_qa_sessions_sets_a_larger_default_page_size() -> None:
    client = DefaultLimitClient()

    records = collect_qa_sessions(
        client,
        start="2026-03-01",
        end="2026-03-31",
        user="example-user",
        extra_params={},
    )

    assert records == []
    assert client.calls == [
        (
            "qa/testlistinstances",
            {"limit": "100", "ordering": "-work_completed", "created_by__username": "example-user"},
        )
    ]


class EarlyStopClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/200/",
            "created": "2026-03-10T10:00:00+10:00",
            "modified": "2026-03-10T10:00:00+10:00",
            "work_started": "2026-03-10T09:00:00+10:00",
            "work_completed": "2026-03-10T10:00:00+10:00",
            "flagged": False,
            "reviewed": "2026-03-10T12:00:00+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
            "created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
        }
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/199/",
            "created": "2026-02-28T10:00:00+10:00",
            "modified": "2026-02-28T10:00:00+10:00",
            "work_started": "2026-02-28T09:00:00+10:00",
            "work_completed": "2026-02-28T10:00:00+10:00",
            "flagged": False,
            "reviewed": "2026-02-28T12:00:00+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
            "created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
        }
        raise AssertionError("collector should have stopped before consuming older pages")

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        if endpoint.endswith("/206/"):
            return {
                "name": "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
        if endpoint.endswith("/2/"):
            return {"name": "LAx - LinacName"}
        raise AssertionError(endpoint)


def test_collect_qa_sessions_stops_after_passing_start_date() -> None:
    client = EarlyStopClient()

    records = collect_qa_sessions(
        client,
        start="2026-03-01",
        end="2026-03-31",
        user="example-user",
        extra_params={},
    )

    assert len(records) == 1
    assert records[0].remote_id == "200"


class CacheReuseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/300/",
            "created": "2026-03-10T10:00:00+10:00",
            "modified": "2026-03-10T10:00:00+10:00",
            "work_started": "2026-03-10T09:00:00+10:00",
            "work_completed": "2026-03-10T10:00:00+10:00",
            "flagged": False,
            "reviewed": "2026-03-10T12:00:00+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
            "created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
        }
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/301/",
            "created": "2026-03-10T11:00:00+10:00",
            "modified": "2026-03-10T11:00:00+10:00",
            "work_started": "2026-03-10T10:30:00+10:00",
            "work_completed": "2026-03-10T11:00:00+10:00",
            "flagged": False,
            "reviewed": "2026-03-10T12:00:00+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
            "created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
        }

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/206/"):
            return {
                "name": "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
        if endpoint.endswith("/2/"):
            return {"name": "LAx - LinacName"}
        raise AssertionError(endpoint)


def test_collect_qa_sessions_reuses_collection_and_unit_cache() -> None:
    client = CacheReuseClient()

    records = collect_qa_sessions(
        client,
        start="2026-03-01",
        end="2026-03-31",
        user="example-user",
        extra_params={},
    )

    assert [record.remote_id for record in records] == ["300", "301"]
    assert client.calls == [
        (
            "qa/testlistinstances",
            {"limit": "100", "ordering": "-work_completed", "created_by__username": "example-user"},
        ),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/", None),
    ]


class ResolvedSearchClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield _qa_session_payload("400", "2026-03-10T10:00:00+10:00", "206")
        yield _qa_session_payload("401", "2026-03-10T11:00:00+10:00", "207")
        yield _qa_session_payload("399", "2026-02-28T10:00:00+10:00", "206")
        raise AssertionError("collector should stop once ordered sessions are older than start")

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/206/"):
            return {
                "name": "Wanted Collection",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
        if endpoint.endswith("/207/"):
            return {
                "name": "Other Collection",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/999/",
            }
        if endpoint.endswith("/2/"):
            return {"name": "LAx - LinacName"}
        if endpoint.endswith("/999/"):
            return {"name": "Should Not Be Fetched"}
        raise AssertionError(endpoint)


def test_collect_resolved_qa_sessions_filters_before_unit_fetch_and_stops_early() -> None:
    client = ResolvedSearchClient()

    sessions = collect_resolved_qa_sessions(
        client,
        start="2026-03-01",
        end="2026-03-31",
        unit="LAx",
        collection_name_matches=lambda name: name.startswith("Wanted"),
    )

    assert [session.session_id for session in sessions] == ["400"]
    assert sessions[0].collection_name == "Wanted Collection"
    assert sessions[0].short_unit_name == "LAx"
    assert client.calls == [
        ("qa/testlistinstances", {"limit": "100", "ordering": "-work_completed"}),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/207/", None),
    ]


class AssignmentScopedClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint == "units/units":
            yield {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/", "name": "LAx - LinacName"}
            yield {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/3/", "name": "LBy - Other"}
            return
        if endpoint == "qa/unittestcollections":
            assert params == {"limit": "100", "unit__name": "LAx - LinacName"}
            yield {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/206/",
                "name": "Wanted Monthly 6 MV",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
            yield {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/207/",
                "name": "Other Assignment",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/2/",
            }
            return
        if endpoint == "qa/testlistinstances":
            assert params is not None
            assert params["unit_test_collection"] == "206"
            yield _qa_session_payload("400", "2026-03-10T10:00:00+10:00", "206")
            yield _qa_session_payload("399", "2026-02-28T10:00:00+10:00", "206")
            raise AssertionError("collector should stop once this assignment is older than start")
        raise AssertionError(endpoint)

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/2/"):
            return {"url": endpoint, "name": "LAx - LinacName"}
        raise AssertionError(endpoint)


def test_assignment_scoped_collection_avoids_broad_session_metadata_scan() -> None:
    client = AssignmentScopedClient()

    collections = collect_unit_test_collections(
        client,
        unit="LAx",
        collection_name_matches=lambda name: name.startswith("Wanted"),
    )
    sessions = collect_resolved_qa_sessions_for_collections(
        client,
        collections,
        start="2026-03-01",
        end="2026-03-31",
    )

    assert [collection.remote_id for collection in collections] == ["206"]
    assert [session.session_id for session in sessions] == ["400"]
    assert ("qa/testlistinstances", {"limit": "100", "ordering": "-work_completed", "unit_test_collection": "206"}) in client.calls
    assert not any(call[0].endswith("/207/") for call in client.calls)


def _qa_session_payload(remote_id: str, work_completed: str, collection_id: str) -> dict:
    return {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/{remote_id}/",
        "created": work_completed,
        "modified": work_completed,
        "work_started": work_completed,
        "work_completed": work_completed,
        "flagged": False,
        "reviewed": work_completed,
        "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/{collection_id}/",
    }


class ServiceEventClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint == "servicelog/serviceevents":
            yield {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/324/",
                "datetime_created": "2026-04-14T15:57:46.240311+10:00",
                "datetime_modified": None,
                "datetime_service": "2026-04-14T14:46:00+10:00",
                "problem_description": "Balloon Tests 3B and 4B have been failing.",
                "work_description": "Elekta replaced the balloon valve.\n\nPerformed Weekly as RTS, as well as RT daily runup. Unit continues to fail balloon tests 3B and 4B. Likely failing to seal balloon assembly against housing.",
                "is_review_required": True,
                "unit_service_area": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/unitserviceareas/61/",
                "service_type": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/servicetypes/2/",
                "service_status": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceeventstatus/1/",
                "user_created_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
            }
            return
        if endpoint == "servicelog/returntoserviceqa":
            for remote_id, collection_id in ((854, 427), (855, 428)):
                yield {
                    "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/returntoserviceqa/{remote_id}/",
                    "service_event": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/324/",
                    "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/{collection_id}/",
                    "test_list_instance": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/14396/",
                }
            return
        raise AssertionError(endpoint)

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/61/"):
            return {
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/39/",
            }
        if endpoint.endswith("/39/"):
            return {"name": "ABC x"}
        if endpoint.endswith("/2/"):
            return {"name": "Repair"}
        if endpoint.endswith("/1/"):
            return {"name": "Submitted"}
        if endpoint.endswith("/427/"):
            return {"name": "ABC Weekly :: Visual Inspection"}
        if endpoint.endswith("/428/"):
            return {"name": "ABC Weekly :: Spirometry"}
        raise AssertionError(endpoint)


def test_collect_service_events_normalizes_service_records() -> None:
    client = ServiceEventClient()

    records = collect_service_events(
        client,
        start="2026-04-01",
        end="2026-04-20",
        extra_params={},
    )

    assert len(records) == 1
    record = records[0]
    assert record.source_type == "service_event"
    assert record.remote_id == "324"
    assert record.performed_at == "2026-04-14T14:46:00+10:00"
    assert record.created_by == "27"
    assert record.unit == "ABC x"
    assert record.title == "Balloon Tests 3B and 4B have been failing."
    assert record.status == "submitted"
    service_event = record.raw["service_event"]
    assert service_event["service_type_name"] == "Repair"
    assert service_event["service_status_name"] == "Submitted"
    assert service_event["event_url"] == "https://radmachine.example/demo-customer/servicelog/event/details/324/"
    assert service_event["return_to_service"] == [
        {
            "label": "ABC Weekly QA",
            "session_url": "https://radmachine.example/demo-customer/qa/session/review/14396/",
            "qa_groups": ["ABC Weekly :: Visual Inspection", "ABC Weekly :: Spirometry"],
        }
    ]
    assert client.calls == [
        ("servicelog/serviceevents", {"limit": "100", "ordering": "-datetime_service"}),
        ("servicelog/returntoserviceqa", {"limit": "100"}),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/427/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/428/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/unitserviceareas/61/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/39/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/servicetypes/2/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceeventstatus/1/", None),
    ]


class ReturnToServiceQAClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/returntoserviceqa/854/",
            "datetime_assigned": "2026-05-25T20:46:46+10:00",
            "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/427/",
            "test_list_instance": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/14396/",
            "user_assigned_by": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/auth/users/27/",
            "service_event": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/329/",
        }
        yield {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/returntoserviceqa/855/",
            "service_event": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/330/",
        }


def test_collect_service_log_return_to_service_qa_filters_by_service_event() -> None:
    client = ReturnToServiceQAClient()
    service_event_url = f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/329/"

    records = collect_service_log_return_to_service_qa(
        client,
        service_event_urls={service_event_url},
        extra_params={"limit": "2"},
    )

    assert len(records) == 1
    assert records[0].remote_id == "854"
    assert records[0].service_event == service_event_url
    assert records[0].unit_test_collection.endswith("/427/")
    assert client.calls == [("servicelog/returntoserviceqa", {"limit": "2"})]

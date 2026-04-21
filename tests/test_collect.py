from __future__ import annotations

from radlog.collect import collect_qa_sessions, collect_service_events
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
            return {"name": "LA7 - Hayman"}
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
    assert record.unit == "LA7"
    assert record.site == "Hayman"
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
            return {"name": "LA7 - Hayman"}
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
            return {"name": "LA7 - Hayman"}
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
            yield {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/returntoserviceqa/854/",
                "service_event": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/324/",
                "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/901/",
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
            return {"name": "ABC 2"}
        if endpoint.endswith("/2/"):
            return {"name": "Repair"}
        if endpoint.endswith("/1/"):
            return {"name": "Submitted"}
        if endpoint.endswith("/901/"):
            return {"name": "ABC Weekly QC"}
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
    assert record.unit == "ABC 2"
    assert record.title == "Balloon Tests 3B and 4B have been failing."
    assert record.status == "submitted"
    service_event = record.raw["service_event"]
    assert service_event["service_type_name"] == "Repair"
    assert service_event["service_status_name"] == "Submitted"
    assert service_event["event_url"] == "https://radmachine.radformation.com/tcc/servicelog/event/details/324/"
    assert service_event["return_to_service_qa"] == ["ABC Weekly QC"]
    assert client.calls == [
        ("servicelog/serviceevents", {"limit": "100", "ordering": "-datetime_service"}),
        ("servicelog/returntoserviceqa", {"limit": "100"}),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/901/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/unitserviceareas/61/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/39/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/servicetypes/2/", None),
        (f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceeventstatus/1/", None),
    ]

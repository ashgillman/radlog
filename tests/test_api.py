from __future__ import annotations

from typing import Any

from radlog.api import RadMachineClient
from radlog.config import Config, ExtensionsConfig, GroupingConfig, LogbookConfig, RadMachineConfig, RenderConfig
from radlog.rm_models import (
    ServiceEvent,
    ServiceLogReturnToServiceQA,
    TestInstance as RmTestInstance,
    TestListInstance as RmTestListInstance,
    Unit,
    UnitTestCollection,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | list[Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any] | list[Any]:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict[str, Any] | list[Any]) -> None:
        self.headers: dict[str, str] = {}
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str] | None, int]] = []

    def get(self, url: str, params: dict[str, str] | None = None, timeout: int = 0) -> FakeResponse:
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


def test_typed_paginated_methods_map_payloads(monkeypatch) -> None:
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret")
    session = FakeSession(
        {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "url": "https://radmachine.example/demo-customer/api/qa/testlistinstances/1/",
                    "work_completed": "2026-03-06T10:10:00+10:00",
                }
            ],
        }
    )
    client = RadMachineClient(_config(), session=session)

    records = list(client.qa_test_list_instances(params={"limit": "1"}))

    assert records == [
        RmTestListInstance.from_api(
            {
                "url": "https://radmachine.example/demo-customer/api/qa/testlistinstances/1/",
                "work_completed": "2026-03-06T10:10:00+10:00",
            }
        )
    ]
    assert session.calls == [
        ("https://radmachine.example/demo-customer/api/qa/testlistinstances", {"limit": "1"}, 30)
    ]


def test_typed_get_methods_map_payloads(monkeypatch) -> None:
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret")
    payload = {
        "url": "https://radmachine.example/demo-customer/api/qa/unittestcollections/206/",
        "name": "Linac Monthly",
    }
    session = FakeSession(payload)
    client = RadMachineClient(_config(), session=session)

    collection = client.qa_unit_test_collection("qa/unittestcollections/206/")

    assert collection == UnitTestCollection.from_api(payload)
    assert session.calls == [
        ("https://radmachine.example/demo-customer/api/qa/unittestcollections/206/", None, 30)
    ]


def test_common_typed_paginated_methods_use_expected_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret")
    session = FakeSession({"count": 0, "next": None, "previous": None, "results": []})
    client = RadMachineClient(_config(), session=session)

    calls = [
        (client.qa_test_instances, "qa/testinstances", RmTestInstance),
        (client.qa_unit_test_collections, "qa/unittestcollections", UnitTestCollection),
        (client.units, "units/units", Unit),
        (client.service_events, "servicelog/serviceevents", ServiceEvent),
        (client.service_log_return_to_service_qa, "servicelog/returntoserviceqa", ServiceLogReturnToServiceQA),
    ]

    for method, endpoint, _model_type in calls:
        assert list(method(params={"limit": "5"})) == []
        assert session.calls[-1] == (
            f"https://radmachine.example/demo-customer/api/{endpoint}",
            {"limit": "5"},
            30,
        )


def _config() -> Config:
    return Config(
        radmachine=RadMachineConfig(base_url="https://radmachine.example", customer_id="demo-customer"),
        logbook=LogbookConfig(),
        grouping=GroupingConfig(),
        render=RenderConfig(),
        extensions=ExtensionsConfig(),
    )

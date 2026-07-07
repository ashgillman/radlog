from __future__ import annotations

from radlog.rm_models import (
    ServiceEvent,
    ServiceLogReturnToServiceQA,
    TestInstance as RmTestInstance,
    TestListInstance as RmTestListInstance,
    Unit,
    UnitTestCollection,
    extract_id,
    split_unit_name,
)


def test_test_list_instance_preserves_raw_and_derives_status() -> None:
    payload = {
        "url": "https://radmachine.example/demo-customer/api/qa/testlistinstances/13162/",
        "site_url": "https://radmachine.example/demo-customer/qa/session/details/13162/",
        "work_started": "2026-03-06T10:00:00+10:00",
        "work_completed": "2026-03-06T10:10:00+10:00",
        "flagged": True,
        "reviewed": False,
        "unit_test_collection": "https://radmachine.example/demo-customer/api/qa/unittestcollections/206/",
        "comments": [{"comment": "Review this"}],
        "test_instances": [{"value": 1}],
        "unexpected": "kept",
    }

    instance = RmTestListInstance.from_api(payload)

    assert instance.remote_id == "13162"
    assert instance.performed_at == "2026-03-06T10:10:00+10:00"
    assert instance.status == "flagged"
    assert instance.comments == [{"comment": "Review this"}]
    assert instance.raw["unexpected"] == "kept"


def test_unit_test_collection_parses_known_links() -> None:
    collection = UnitTestCollection.from_api(
        {
            "url": "https://radmachine.example/demo-customer/api/qa/unittestcollections/206/",
            "name": "Linac Monthly",
            "unit": "https://radmachine.example/demo-customer/api/units/units/2/",
            "frequency": "https://radmachine.example/demo-customer/api/qa/frequencies/3/",
        }
    )

    assert collection.remote_id == "206"
    assert collection.name == "Linac Monthly"
    assert collection.unit.endswith("/2/")
    assert collection.frequency.endswith("/3/")


def test_unit_splits_radmachine_unit_name() -> None:
    unit = Unit.from_api({"url": "https://radmachine.example/demo-customer/api/units/units/2/", "name": "LAx - LinacName"})

    assert unit.short_name_and_site == ("LAx", "LinacName")
    assert split_unit_name("ABC x") == ("ABC x", None)


def test_service_event_derives_performed_at() -> None:
    event = ServiceEvent.from_api(
        {
            "url": "https://radmachine.example/demo-customer/api/servicelog/serviceevents/324/",
            "datetime_created": "2026-04-14T15:57:46+10:00",
            "datetime_service": "2026-04-14T14:46:00+10:00",
            "problem_description": "Problem",
            "user_created_by": "https://radmachine.example/demo-customer/api/auth/users/27/",
        }
    )

    assert event.remote_id == "324"
    assert event.performed_at == "2026-04-14T14:46:00+10:00"
    assert extract_id(event.user_created_by) == "27"


def test_other_api_models_are_tolerant_of_partial_payloads() -> None:
    test_instance = RmTestInstance.from_api({"url": "https://radmachine.example/demo-customer/api/qa/testinstances/99/"})

    assert test_instance.remote_id == "99"
    assert test_instance.value is None


def test_service_log_return_to_service_qa_parses_real_endpoint_shape() -> None:
    item = ServiceLogReturnToServiceQA.from_api(
        {
            "url": "https://radmachine.example/demo-customer/api/servicelog/returntoserviceqa/854/",
            "datetime_assigned": "2026-05-25T20:46:46+10:00",
            "unit_test_collection": "https://radmachine.example/demo-customer/api/qa/unittestcollections/427/",
            "test_list_instance": "https://radmachine.example/demo-customer/api/qa/testlistinstances/14396/",
            "user_assigned_by": "https://radmachine.example/demo-customer/api/auth/users/27/",
            "service_event": "https://radmachine.example/demo-customer/api/servicelog/serviceevents/329/",
            "unexpected": "kept",
        }
    )

    assert item.remote_id == "854"
    assert item.service_event.endswith("/329/")
    assert item.unit_test_collection.endswith("/427/")
    assert item.test_list_instance.endswith("/14396/")
    assert item.raw["unexpected"] == "kept"

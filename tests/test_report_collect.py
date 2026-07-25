from __future__ import annotations

from radlog.report_collect import collect_abnormal_qa_report, flatten_test_list
from radlog.report_models import ReportCollectionProfile

from tests.support import TEST_BASE_URL, TEST_CUSTOMER_ID


class AbnormalReportClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        assert endpoint == "qa/testlistinstances"
        yield _session_payload(
            "101",
            "2026-07-20T10:00:00+10:00",
            collection_id="201",
            test_list_id="301",
            test_instances=[
                {
                    "order": 0,
                    "value": 100.1,
                    "pass_fail": "ok",
                    "comment": "",
                    "skipped": False,
                    "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testinstances/1/",
                },
                {
                    "order": 1,
                    "value": 4.2,
                    "pass_fail": "fail",
                    "comment": "Investigated and repeated.",
                    "skipped": False,
                    "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testinstances/2/",
                },
                {
                    "order": 2,
                    "value": 2.1,
                    "pass_fail": "warning",
                    "comment": "",
                    "skipped": False,
                    "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testinstances/3/",
                },
                {
                    "order": 3,
                    "value": None,
                    "pass_fail": "not_done",
                    "comment": "",
                    "skipped": True,
                    "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testinstances/4/",
                },
            ],
            comments=[{"comment": "Session-level note."}],
        )
        yield _session_payload(
            "102",
            "2026-07-10T10:00:00+10:00",
            collection_id="201",
            test_list_id="301",
            test_instances=[],
        )

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/201/"):
            return {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/201/",
                "name": "Generic Monthly QA",
                "unit": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/11/",
            }
        if endpoint.endswith("/11/"):
            return {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/units/11/",
                "name": "LINAC-A - SiteName",
                "type": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/units/unittypes/4/",
            }
        if "testlists-details/301" in endpoint:
            return {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists-details/301/",
                "name": "Generic Monthly QA",
                "tests": [
                    {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/401/", "name": "Nominal output"},
                ],
                "test_lists": [
                    {
                        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists-details/302/",
                        "name": "Nested Section",
                        "tests": [
                            {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/402/", "name": "Failing geometry"},
                            {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/403/", "name": "Near tolerance"},
                            {"url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/404/", "name": "Skipped item"},
                        ],
                        "test_lists": [],
                    }
                ],
            }
        if endpoint.endswith("/301/"):
            return {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/301/",
                "name": "Generic Monthly QA",
                "tests": [
                    f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/401/",
                ],
                "test_lists": [
                    f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/302/",
                ],
            }
        if endpoint.endswith("/302/"):
            return {
                "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/302/",
                "name": "Nested Section",
                "tests": [
                    f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/402/",
                    f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/403/",
                    f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/404/",
                ],
                "test_lists": [],
            }
        if endpoint.endswith("/401/"):
            return {"url": endpoint, "name": "Nominal output", "slug": "nominal_output"}
        if endpoint.endswith("/402/"):
            return {"url": endpoint, "name": "Failing geometry", "slug": "failing_geometry"}
        if endpoint.endswith("/403/"):
            return {"url": endpoint, "name": "Near tolerance", "slug": "near_tolerance"}
        if endpoint.endswith("/404/"):
            return {"url": endpoint, "name": "Skipped item", "slug": "skipped_item"}
        raise AssertionError(endpoint)


def test_collect_abnormal_qa_report_extracts_fails_warnings_and_comments() -> None:
    client = AbnormalReportClient()
    profile = ReportCollectionProfile()

    report = collect_abnormal_qa_report(client, start="2026-07-14", end="2026-07-21", profile=profile)

    assert report.start == "2026-07-14"
    assert report.end == "2026-07-21"
    assert len(report.issues) == 3
    assert [issue.test_label for issue in report.issues] == ["Failing geometry", "Near tolerance", "Session comment"]
    assert [issue.issue_type for issue in report.issues] == ["action", "tolerance", "comment"]
    assert report.issues[0].comment == "Investigated and repeated."
    assert report.issues[2].comment == "Session-level note."
    assert report.issues[0].equipment_name == "LINAC-A - SiteName"
    assert report.issues[0].equipment_group == "LINAC-A"
    assert report.issues[0].collection_name == "Generic Monthly QA"
    assert report.issues[0].session_id == "101"
    assert client.calls[0] == (
        "qa/testlistinstances",
        {"limit": "100", "ordering": "-work_completed"},
    )
    assert profile.sessions_seen == 2
    assert profile.sessions_in_range == 1
    assert profile.sessions_with_issues == 1
    assert profile.metadata_fetches == 3
    assert profile.test_lists_flattened == 2
    fetched = [call[0] for call in client.calls]
    assert "qa/testlists-details/301/" in fetched
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/302/" not in fetched
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/401/" not in fetched
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/402/" not in fetched
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/403/" not in fetched
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/tests/404/" not in fetched


def test_flatten_test_list_returns_depth_first_test_labels() -> None:
    client = AbnormalReportClient()

    labels = [test.label for test in flatten_test_list(client, f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/301/")]

    assert labels == ["Nominal output", "Failing geometry", "Near tolerance", "Skipped item"]


def test_collect_abnormal_qa_report_skips_metadata_fetches_for_normal_sessions() -> None:
    class NormalSessionClient:
        def paginate(self, endpoint: str, params: dict[str, str] | None = None):
            yield _session_payload(
                "103",
                "2026-07-20T10:00:00+10:00",
                collection_id="201",
                test_list_id="301",
                test_instances=[
                    {
                        "order": 0,
                        "value": 100.0,
                        "pass_fail": "ok",
                        "comment": "",
                        "skipped": False,
                    }
                ],
            )

        def get_json(self, endpoint: str, params: dict[str, str] | None = None):
            raise AssertionError(f"Unexpected metadata fetch for normal session: {endpoint}")

    report = collect_abnormal_qa_report(NormalSessionClient(), start="2026-07-14", end="2026-07-21")

    assert report.issues == []


def test_collect_abnormal_qa_report_reuses_flattened_test_lists() -> None:
    class RepeatedTestListClient(AbnormalReportClient):
        def paginate(self, endpoint: str, params: dict[str, str] | None = None):
            self.calls.append((endpoint, params))
            for remote_id in ("101", "102"):
                yield _session_payload(
                    remote_id,
                    "2026-07-20T10:00:00+10:00",
                    collection_id="201",
                    test_list_id="301",
                    test_instances=[
                        {
                            "order": 1,
                            "value": 4.2,
                            "pass_fail": "fail",
                            "comment": "",
                            "skipped": False,
                        }
                    ],
                )

    client = RepeatedTestListClient()
    profile = ReportCollectionProfile()

    report = collect_abnormal_qa_report(client, start="2026-07-14", end="2026-07-21", profile=profile)

    assert len(report.issues) == 2
    assert profile.test_lists_flattened == 2
    assert [call[0] for call in client.calls].count("qa/testlists-details/301/") == 1
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/301/" not in [call[0] for call in client.calls]
    assert f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/302/" not in [call[0] for call in client.calls]


def _session_payload(
    remote_id: str,
    work_completed: str,
    *,
    collection_id: str,
    test_list_id: str,
    test_instances: list[dict],
    comments: list[dict] | None = None,
) -> dict:
    return {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/{remote_id}/",
        "site_url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/qa/session/details/{remote_id}/",
        "work_started": work_completed,
        "work_completed": work_completed,
        "flagged": any(test.get("pass_fail") in {"fail", "warning"} for test in test_instances),
        "reviewed": True,
        "unit_test_collection": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/unittestcollections/{collection_id}/",
        "test_list": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/{test_list_id}/",
        "comments": comments or [],
        "test_instances": test_instances,
    }

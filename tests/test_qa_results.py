from __future__ import annotations

from radlog.qa_results import numeric_test_value_by_slug
from radlog.rm_models import TestListInstance as RmTestListInstance

from tests.support import TEST_BASE_URL, TEST_CUSTOMER_ID


class FakeTestListDetailsClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        assert endpoint == "qa/testlists-details/301/"
        return {
            "tests": [{"slug": "sliding_window"}],
            "test_lists": [
                {
                    "tests": [{"slug": "linac_monthly_output_deviation_6_mv"}],
                    "test_lists": [],
                }
            ],
        }


def test_numeric_test_value_by_slug_uses_testlist_details_when_result_has_no_slug() -> None:
    client = FakeTestListDetailsClient()
    session = RmTestListInstance.from_api(
        {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/15073/",
            "test_list": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlists/301/",
            "test_instances": [
                {"order": 0, "value": 9.999, "skipped": False},
                {"order": 1, "value": 0.1179, "skipped": False},
            ],
        }
    )

    value = numeric_test_value_by_slug(
        session,
        "linac_monthly_output_deviation_6_mv",
        client=client,
    )

    assert value == 0.1179
    assert client.calls == [("qa/testlists-details/301/", None)]


def test_numeric_test_value_by_slug_uses_direct_embedded_slug_without_client() -> None:
    session = RmTestListInstance.from_api(
        {
            "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/15073/",
            "test_instances": [
                {"slug": "linac_monthly_output_deviation_6_mv", "value": 0.1179, "skipped": False},
            ],
        }
    )

    assert numeric_test_value_by_slug(session, "linac_monthly_output_deviation_6_mv") == 0.1179

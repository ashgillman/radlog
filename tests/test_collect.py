from __future__ import annotations

from radlog.collect import collect_qa_sessions


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def paginate(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        yield {
            "url": "https://radmachine.radformation.com/tcc/api/qa/testlistinstances/13162/",
            "created": "2026-03-06T10:10:59+10:00",
            "modified": "2026-03-06T10:10:59+10:00",
            "work_started": "2026-03-06T10:06:00+10:00",
            "work_completed": "2026-03-06T10:10:58+10:00",
            "flagged": False,
            "reviewed": "2026-03-09T11:14:03+10:00",
            "unit_test_collection": "https://radmachine.radformation.com/tcc/api/qa/unittestcollections/206/",
            "created_by": "https://radmachine.radformation.com/tcc/api/auth/users/27/",
        }

    def get_json(self, endpoint: str, params: dict[str, str] | None = None):
        self.calls.append((endpoint, params))
        if endpoint.endswith("/206/"):
            return {
                "name": "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
                "unit": "https://radmachine.radformation.com/tcc/api/units/units/2/",
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
        user="gillmanas",
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
    assert client.calls[0] == (
        "qa/testlistinstances",
        {"limit": "5", "ordering": "-work_completed", "created_by__username": "gillmanas"},
    )

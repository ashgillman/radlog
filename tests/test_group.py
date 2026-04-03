from __future__ import annotations

from radlog.group import group_source_records
from radlog.models import SourceRecord


def test_group_source_records_merges_linac_monthly_sessions() -> None:
    records = [
        SourceRecord(
            source_type="qa_session",
            remote_id="13162",
            performed_at="2026-03-06T10:10:58+10:00",
            unit="LA7",
            site="Hayman",
            title="Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
        ),
        SourceRecord(
            source_type="qa_session",
            remote_id="13167",
            performed_at="2026-03-06T11:04:55+10:00",
            unit="LA7",
            site="Hayman",
            title="Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
        ),
    ]

    entries = group_source_records(records)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "linac_mqc"
    assert entry.group_key == "2026-03-06_LA7_linac_monthly"
    assert entry.title == "LA7 MQC"
    assert entry.source_ids == ["qa:13162", "qa:13167"]
    assert [item.label for item in entry.performed_items] == [
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
    ]


def test_group_source_records_keeps_non_monthly_sessions_separate() -> None:
    records = [
        SourceRecord(
            source_type="qa_session",
            remote_id="13162",
            performed_at="2026-03-06T10:10:58+10:00",
            unit="LA7",
            site="Hayman",
            title="Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
        ),
        SourceRecord(
            source_type="qa_session",
            remote_id="13170",
            performed_at="2026-03-06T12:00:00+10:00",
            unit="LA7",
            site="Hayman",
            title="Reference dosimetry :: Photons :: 6 MV",
        ),
    ]

    entries = group_source_records(records)

    assert len(entries) == 2
    assert {entry.entry_type for entry in entries} == {"linac_mqc", "qa_session"}

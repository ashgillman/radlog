from __future__ import annotations

from radlog.group import group_source_records
from radlog.models import SourceRecord


def _record(
    remote_id: str,
    performed_at: str,
    unit: str,
    site: str,
    title: str,
    *,
    frequency: str | None = None,
    due_date: str | None = None,
) -> SourceRecord:
    raw: dict[str, object] = {}
    if frequency or due_date:
        raw["unit_test_collection"] = {
            "frequency": frequency,
            "due_date": due_date,
        }
    return SourceRecord(
        source_type="qa_session",
        remote_id=remote_id,
        performed_at=performed_at,
        unit=unit,
        site=site,
        title=title,
        raw=raw,
    )


def test_group_source_records_merges_linac_monthly_sessions() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    records = [
        _record(
            "13162",
            "2026-03-06T10:10:58+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
            frequency=monthly_frequency,
        ),
        _record(
            "13167",
            "2026-03-06T11:04:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
            frequency=monthly_frequency,
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
        "Output and relative dosimetry :: 10 MV",
        "Output and relative dosimetry :: 6 MV",
    ]


def test_group_source_records_keeps_non_monthly_sessions_separate() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    records = [
        _record(
            "13162",
            "2026-03-06T10:10:58+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
            frequency=monthly_frequency,
        ),
        _record(
            "13170",
            "2026-03-06T12:00:00+10:00",
            "LA7",
            "Hayman",
            "Reference dosimetry :: Photons :: 6 MV",
        ),
    ]

    entries = group_source_records(records)

    assert len(entries) == 2
    assert {entry.entry_type for entry in entries} == {"linac_mqc", "qa_session"}


def test_group_source_records_uses_monthly_collection_metadata_for_linac_mqc() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    monthly_due_date = "2026-04-01T08:00:00+10:00"
    records = [
        _record(
            "13452",
            "2026-03-30T08:00:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Imaging :: CatPhan 503 :: SFOV CW",
            frequency=monthly_frequency,
            due_date=monthly_due_date,
        ),
        _record(
            "13460",
            "2026-03-30T09:08:00+10:00",
            "LA7",
            "Hayman",
            "Winston Lutz :: eQA :: 6 MV",
            frequency=monthly_frequency,
            due_date=monthly_due_date,
        ),
        _record(
            "13465",
            "2026-03-30T11:47:00+10:00",
            "LA7",
            "Hayman",
            "EPID image quality (PTW EPID QC)",
            frequency=monthly_frequency,
            due_date="2026-04-01T11:28:42+10:00",
        ),
        _record(
            "13499",
            "2026-03-31T08:00:00+10:00",
            "ABC 1",
            None,
            "ABC Weekly QC",
            frequency="https://radmachine.radformation.com/tcc/api/qa/frequencies/2/",
            due_date="2026-03-31T08:00:00+10:00",
        ),
        _record(
            "13577",
            "2026-04-02T08:00:00+10:00",
            "PTW Quickcheck: 3534",
            None,
            "Quickcheck Data Download",
        ),
    ]

    entries = group_source_records(records)

    linac_entries = [entry for entry in entries if entry.entry_type == "linac_mqc"]
    assert len(linac_entries) == 1
    linac_entry = linac_entries[0]
    assert linac_entry.group_key == "2026-03-30_LA7_linac_monthly"
    assert linac_entry.source_ids == ["qa:13452", "qa:13460", "qa:13465"]
    assert [(item.category, item.label) for item in linac_entry.performed_items] == [
        ("Imaging", "SFOV CW"),
        ("Winston Lutz", "6 MV"),
        ("EPID Image Quality", "Contrast visibility"),
    ]
    assert {entry.title for entry in entries if entry.entry_type == "qa_session"} == {
        "ABC Weekly QC",
        "Quickcheck Data Download",
    }


def test_group_source_records_avoids_duplicate_monthly_item_names() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    records = [
        _record(
            "13462",
            "2026-03-30T11:26:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Mechanical",
            frequency=monthly_frequency,
        ),
        _record(
            "13463",
            "2026-03-30T11:28:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Safety and Functionality",
            frequency=monthly_frequency,
        ),
    ]

    entries = group_source_records(records)

    entry = next(entry for entry in entries if entry.entry_type == "linac_mqc")
    assert [(item.category, item.label) for item in entry.performed_items] == [
        ("Mechanical", "Machine mechanical measurements"),
        ("Safety and Functionality", "Mechanical drive and interlocks"),
    ]

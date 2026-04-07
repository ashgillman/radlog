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


def test_group_source_records_folds_same_day_reference_dosimetry_into_existing_monthly_group() -> None:
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

    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "linac_mqc"
    assert [(item.category, item.label) for item in entry.performed_items] == [
        ("Dosimetry", "Output and relative dosimetry :: 10 MV"),
        ("Ad hoc", "Reference dosimetry :: Photons :: 6 MV"),
    ]


def test_group_source_records_groups_abc_weekly_entries() -> None:
    records = [
        _record(
            "14001",
            "2026-04-07T08:00:00+10:00",
            "ABC 1",
            None,
            "ABC Weekly QC",
        ),
        _record(
            "14002",
            "2026-04-07T08:15:00+10:00",
            "ABC 1",
            None,
            "ABC Weekly QC",
        ),
    ]

    entries = group_source_records(records)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "abc_weekly"
    assert entry.group_key == "2026-04-07_ABC 1_abc_weekly"
    assert entry.title == "ABC 1 Weekly QA"
    assert entry.source_ids == ["qa:14001", "qa:14002"]


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
        ("Imaging", "CatPhan 503 (SFOV CW)"),
        ("Winston Lutz", "6 MV"),
        ("EPID Image Quality", "Contrast visibility"),
    ]
    assert {entry.title for entry in entries if entry.entry_type == "qa_session"} == {
        "Quickcheck Data Download",
    }
    assert {entry.title for entry in entries if entry.entry_type == "abc_weekly"} == {
        "ABC 1 Weekly QA",
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


def test_group_source_records_collapses_linac_monthly_items_into_authored_summary() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    records = [
        _record(
            "13446",
            "2026-03-30T07:46:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Imaging :: CatPhan 503 :: MFOV CCW",
            frequency=monthly_frequency,
        ),
        _record(
            "13452",
            "2026-03-30T08:00:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Imaging :: CatPhan 503 :: SFOV CW",
            frequency=monthly_frequency,
        ),
        _record(
            "13454",
            "2026-03-30T08:03:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Imaging :: CatPhan 503 :: SFOV CCW",
            frequency=monthly_frequency,
        ),
        _record(
            "13455",
            "2026-03-30T08:05:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Imaging :: CatPhan 503 :: MFOV CW",
            frequency=monthly_frequency,
        ),
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
        _record(
            "13464",
            "2026-03-30T11:39:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Geometry :: Jaw drive accuracy",
            frequency=monthly_frequency,
        ),
        _record(
            "13466",
            "2026-03-30T11:55:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Geometry :: EPID scaling",
            frequency=monthly_frequency,
        ),
        _record(
            "13467",
            "2026-03-30T12:18:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Geometry :: Light vs radiation",
            frequency=monthly_frequency,
        ),
        _record(
            "13469",
            "2026-03-30T12:52:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Leaf speed constancy",
            frequency=monthly_frequency,
        ),
        _record(
            "13470",
            "2026-03-30T12:56:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Sliding window fluence uniformity",
            frequency=monthly_frequency,
        ),
        _record(
            "13471",
            "2026-03-30T13:04:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence",
            frequency=monthly_frequency,
        ),
        _record(
            "13472",
            "2026-03-30T13:08:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to G :: Gantry 0",
            frequency=monthly_frequency,
        ),
        _record(
            "13473",
            "2026-03-30T13:10:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to G :: Gantry 270",
            frequency=monthly_frequency,
        ),
        _record(
            "13474",
            "2026-03-30T13:12:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to G :: Gantry 90",
            frequency=monthly_frequency,
        ),
        _record(
            "13475",
            "2026-03-30T13:15:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to T :: Gantry 0",
            frequency=monthly_frequency,
        ),
        _record(
            "13476",
            "2026-03-30T13:16:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to T :: Gantry 270",
            frequency=monthly_frequency,
        ),
        _record(
            "13477",
            "2026-03-30T13:18:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: MLC :: Picket Fence :: Panel to T :: Gantry 90",
            frequency=monthly_frequency,
        ),
    ]

    entry = group_source_records(records)[0]

    assert [(item.category, item.label) for item in entry.performed_items] == [
        ("Imaging", "CatPhan 503 (MFOV+SFOV x CW+CCW)"),
        ("Mechanical", "Machine mechanical measurements"),
        ("Safety and Functionality", "Mechanical drive and interlocks"),
        ("Geometry", "EPID scaling, light vs. radiation, jaw drive accuracy"),
        ("MLC", "Leaf speed constancy, DRGS, Picket fence by gantry angle"),
    ]


def test_group_source_records_folds_same_day_reference_dosimetry_into_linac_monthly_ad_hoc() -> None:
    monthly_frequency = "https://radmachine.radformation.com/tcc/api/qa/frequencies/3/"
    records = [
        _record(
            "14100",
            "2026-04-07T10:00:00+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Safety and Functionality",
            frequency=monthly_frequency,
        ),
        _record(
            "14101",
            "2026-04-07T14:00:00+10:00",
            "LA7",
            "Hayman",
            "Reference dosimetry :: Photons :: 10 MV",
        ),
    ]

    entries = group_source_records(records)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "linac_mqc"
    assert [(item.category, item.label) for item in entry.performed_items] == [
        ("Safety and Functionality", "Mechanical drive and interlocks"),
        ("Ad hoc", "Reference dosimetry :: Photons :: 10 MV"),
    ]


def test_group_source_records_promotes_monthly_linac_to_post_pmi_when_full_dosimetry_is_present() -> None:
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
        _record(
            "13168",
            "2026-03-06T11:14:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 6 MeV",
            frequency=monthly_frequency,
        ),
        _record(
            "13169",
            "2026-03-06T11:24:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 8 MeV",
            frequency=monthly_frequency,
        ),
        _record(
            "13172",
            "2026-03-06T11:26:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 10 MeV",
            frequency=monthly_frequency,
        ),
        _record(
            "13173",
            "2026-03-06T11:28:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 12 MeV",
            frequency=monthly_frequency,
        ),
        _record(
            "13174",
            "2026-03-06T11:30:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 15 MeV",
            frequency=monthly_frequency,
        ),
        _record(
            "13175",
            "2026-03-06T11:32:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Photon profile constancy",
            frequency=monthly_frequency,
        ),
        _record(
            "13176",
            "2026-03-06T11:33:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Electron profile constancy",
            frequency=monthly_frequency,
        ),
        SourceRecord(
            source_type="qa_session",
            remote_id="13170",
            performed_at="2026-03-06T11:34:55+10:00",
            unit="LA7",
            site="Hayman",
            title="Linac Monthly :: MLC :: Picket Fence :: Panel to G :: Gantry 270",
            raw={
                "unit_test_collection": {
                    "frequency": monthly_frequency,
                },
                "session": {
                    "comments": [
                        {"comment": "Peripheral leaf flagging tol, not clinically of high relevance"}
                    ]
                },
            },
        ),
        _record(
            "13177",
            "2026-03-06T11:36:55+10:00",
            "LA7",
            "Hayman",
            "Linac Monthly :: Dosimetry :: Quickcheck Constancy",
            frequency=monthly_frequency,
        ),
        SourceRecord(
            source_type="qa_session",
            remote_id="13171",
            performed_at="2026-03-06T11:44:55+10:00",
            unit="LA7",
            site="Hayman",
            title="Linac Monthly :: Dosimetry :: Photon profile constancy",
            raw={
                "unit_test_collection": {
                    "frequency": monthly_frequency,
                },
                "session": {
                    "comments": [
                        {
                            "comment": "Discussed results with AB. Both 6X and 10X symmetry are fair laterally."
                        }
                    ]
                },
            },
        ),
    ]

    entry = group_source_records(records)[0]

    assert entry.entry_type == "post_pmi"
    assert entry.group_key == "2026-03-06_LA7_post_pmi"
    assert entry.title == "LA7 post-PMI"
    assert "Linac ready for clinical use. Re-enable energies and document on MOSAIQ." in entry.notable_prompts
    assert [(item.category, item.label) for item in entry.performed_items] == [
        ("MLC", "Picket fence by gantry angle"),
        ("Dosimetry", "Photon and electron profile, output and energy constancy, all energies"),
        ("Dosimetry", "Quickcheck Constancy"),
    ]
    assert "Photon profile constancy\n  - Discussed results with AB. Both 6X and 10X symmetry are fair laterally." in entry.notable_prompts
    assert "Picket Fence: Gantry 270 Panel to G\n  - Peripheral leaf flagging tol, not clinically of high relevance" in entry.notable_prompts

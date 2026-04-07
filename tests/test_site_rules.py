from __future__ import annotations

from radlog.models import SourceRecord
from radlog.models import PerformedItem
from radlog.site_rules import aggregate_performed_items, map_performed_item


def _record(title: str) -> SourceRecord:
    return SourceRecord(
        source_type="qa_session",
        remote_id="1",
        performed_at="2026-03-30T08:00:00+10:00",
        unit="LA7",
        site="Hayman",
        title=title,
    )


def test_map_performed_item_formats_linac_monthly_imaging() -> None:
    item = map_performed_item(
        _record("Linac Monthly :: Imaging :: CatPhan 503 :: MFOV CCW"),
        "linac_mqc",
    )

    assert item.category == "Imaging"
    assert item.label == "MFOV CCW"


def test_map_performed_item_formats_linac_monthly_pickett_fence() -> None:
    item = map_performed_item(
        _record("Linac Monthly :: MLC :: Picket Fence :: Panel to G :: Gantry 270"),
        "linac_mqc",
    )

    assert item.category == "MLC"
    assert item.label == "Picket Fence: Gantry 270 Panel to G"


def test_map_performed_item_preserves_generic_titles_outside_linac_mqc() -> None:
    item = map_performed_item(_record("Quickcheck Data Download"), "qa_session")

    assert item.category == "QA"
    assert item.label == "Quickcheck Data Download"


def test_aggregate_performed_items_collapses_linac_mqc_summary_lines() -> None:
    items = [
        PerformedItem(category="Imaging", label="MFOV CCW"),
        PerformedItem(category="Imaging", label="SFOV CW"),
        PerformedItem(category="Imaging", label="SFOV CCW"),
        PerformedItem(category="Imaging", label="MFOV CW"),
        PerformedItem(category="Mechanical", label="Machine mechanical measurements"),
        PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks"),
        PerformedItem(category="Geometry", label="EPID scaling"),
        PerformedItem(category="Geometry", label="Light vs radiation"),
        PerformedItem(category="Geometry", label="Jaw drive accuracy"),
        PerformedItem(category="MLC", label="Leaf speed constancy"),
        PerformedItem(category="MLC", label="Sliding window fluence uniformity"),
        PerformedItem(category="MLC", label="Picket Fence: Gantry 270 Panel to G"),
    ]

    summary = aggregate_performed_items("linac_mqc", items)

    assert [(item.category, item.label) for item in summary] == [
        ("Imaging", "CatPhan 503 (MFOV+SFOV x CW+CCW)"),
        ("Mechanical", "Machine mechanical measurements"),
        ("Safety and Functionality", "Mechanical drive and interlocks"),
        ("Geometry", "EPID scaling, light vs. radiation, jaw drive accuracy"),
        ("MLC", "Leaf speed constancy, DRGS, Picket fence by gantry angle"),
    ]


def test_aggregate_performed_items_collapses_post_pmi_dosimetry_summary_lines() -> None:
    items = [
        PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks"),
        PerformedItem(category="MLC", label="Leaf speed constancy"),
        PerformedItem(category="MLC", label="Sliding window fluence uniformity"),
        PerformedItem(category="MLC", label="Picket Fence: Gantry 270 Panel to G"),
        PerformedItem(category="Dosimetry", label="Photon profile constancy"),
        PerformedItem(category="Dosimetry", label="Electron profile constancy"),
        PerformedItem(category="Dosimetry", label="Output and energy constancy :: 15 MeV"),
        PerformedItem(category="Dosimetry", label="Output and energy constancy :: 12 MeV"),
        PerformedItem(category="Dosimetry", label="Output and energy constancy :: 10 MeV"),
        PerformedItem(category="Dosimetry", label="Output and energy constancy :: 8 MeV"),
        PerformedItem(category="Dosimetry", label="Output and energy constancy :: 6 MeV"),
        PerformedItem(category="Dosimetry", label="Output and relative dosimetry :: 6 MV"),
        PerformedItem(category="Dosimetry", label="Output and relative dosimetry :: 10 MV"),
        PerformedItem(category="Dosimetry", label="Quickcheck Constancy"),
    ]

    summary = aggregate_performed_items("post_pmi", items)

    assert [(item.category, item.label) for item in summary] == [
        ("Safety and Functionality", "Mechanical drive and interlocks"),
        ("MLC", "Leaf speed constancy, DRGS, Picket fence by gantry angle"),
        ("Dosimetry", "Photon and electron profile, output and energy constancy, all energies"),
        ("Dosimetry", "Quickcheck Constancy"),
    ]

from __future__ import annotations

from radlog.models import SourceRecord
from radlog.site_rules import map_performed_item


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

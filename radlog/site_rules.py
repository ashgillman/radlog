"""Site-specific rules for grouping and display.

New sites should treat this module as the main place to adapt local naming,
equipment conventions, and similar department-specific behavior.
"""

from __future__ import annotations

from .models import PerformedItem, SourceRecord


def equipment_group(record: SourceRecord) -> str | None:
    """Return a broad equipment group for the record."""
    unit = record.unit or ""
    if unit.startswith("LA"):
        return "linac"
    return None


def collection_frequency_name(record: SourceRecord) -> str | None:
    """Return a normalized frequency name for the linked collection."""
    collection = record.raw.get("unit_test_collection", {})
    if not isinstance(collection, dict):
        return None

    frequency = collection.get("frequency")
    if not isinstance(frequency, str):
        return None

    frequency_id = frequency.rstrip("/").rsplit("/", 1)[-1]
    if frequency_id == "3":
        return "monthly"

    return None


def map_performed_item(record: SourceRecord, entry_type: str) -> PerformedItem:
    """Map a source record to the displayed performed-item text."""
    if entry_type == "linac_mqc":
        return _map_linac_mqc_performed_item(record)

    title = record.title or record.remote_id
    return PerformedItem(category="QA", label=title)


def _map_linac_mqc_performed_item(record: SourceRecord) -> PerformedItem:
    title = (record.title or record.remote_id).strip()

    if title.startswith("Linac Monthly :: Imaging :: CatPhan 503 :: "):
        scan = title.removeprefix("Linac Monthly :: Imaging :: CatPhan 503 :: ").strip()
        return PerformedItem(category="Imaging", label=scan)

    if title == "Winston Lutz :: eQA :: 6 MV":
        return PerformedItem(category="Winston Lutz", label="6 MV")

    if title == "Linac Monthly :: Mechanical":
        return PerformedItem(category="Mechanical", label="Machine mechanical measurements")

    if title == "Linac Monthly :: Safety and Functionality":
        return PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks")

    if title.startswith("Linac Monthly :: Geometry :: "):
        label = title.removeprefix("Linac Monthly :: Geometry :: ").strip()
        return PerformedItem(category="Geometry", label=label)

    if title.startswith("Linac Monthly :: Dosimetry :: "):
        label = title.removeprefix("Linac Monthly :: Dosimetry :: ").strip()
        return PerformedItem(category="Dosimetry", label=label)

    if title == "EPID image quality (PTW EPID QC)":
        return PerformedItem(category="EPID Image Quality", label='Contrast visibility')

    if title == "Linac Monthly :: MLC :: Leaf speed constancy":
        return PerformedItem(category="MLC", label="Leaf speed constancy")

    if title == "Linac Monthly :: MLC :: Sliding window fluence uniformity":
        return PerformedItem(category="MLC", label="Sliding window fluence uniformity")

    if title == "Linac Monthly :: MLC :: VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence":
        return PerformedItem(
            category="MLC",
            label="VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence",
        )

    if title.startswith("Linac Monthly :: MLC :: Picket Fence :: "):
        parts = [part.strip() for part in title.split("::")]
        if len(parts) >= 5:
            panel = parts[3]
            gantry = parts[4]
            return PerformedItem(category="MLC", label=f"Picket Fence: {gantry} {panel}")

    if title.startswith("Linac Monthly :: MLC :: "):
        label = title.removeprefix("Linac Monthly :: MLC :: ").strip()
        return PerformedItem(category="MLC", label=label)

    parts = [part.strip() for part in title.split("::")]
    if len(parts) == 1:
        return PerformedItem(category="QA", label=title)
    return PerformedItem(category=parts[0], label=" :: ".join(parts[1:]))

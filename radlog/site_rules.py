"""Site-specific rules for grouping and display.

New sites should treat this module as the main place to adapt local naming,
equipment conventions, and similar department-specific behavior.
"""

from __future__ import annotations

from collections.abc import Iterable

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


def aggregate_performed_items(entry_type: str, items: Iterable[PerformedItem]) -> list[PerformedItem]:
    """Collapse mapped items into authored summaries where useful."""
    item_list = list(items)
    if entry_type == "linac_mqc":
        return _aggregate_linac_mqc_items(item_list)
    return item_list


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


def _aggregate_linac_mqc_items(items: list[PerformedItem]) -> list[PerformedItem]:
    grouped: list[PerformedItem] = []
    handled: set[tuple[str, str]] = set()

    imaging_labels = {item.label for item in items if item.category == "Imaging"}
    if imaging_labels:
        grouped.append(PerformedItem(category="Imaging", label=_summarize_catphan_scans(imaging_labels)))
        handled.update({("Imaging", label) for label in imaging_labels})

    if any(item.category == "Winston Lutz" for item in items):
        grouped.append(PerformedItem(category="Winston Lutz", label="6 MV"))
        handled.update({(item.category, item.label) for item in items if item.category == "Winston Lutz"})

    if any(item.category == "Mechanical" for item in items):
        grouped.append(PerformedItem(category="Mechanical", label="Machine mechanical measurements"))
        handled.update({(item.category, item.label) for item in items if item.category == "Mechanical"})

    if any(item.category == "Safety and Functionality" for item in items):
        grouped.append(
            PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks")
        )
        handled.update(
            {(item.category, item.label) for item in items if item.category == "Safety and Functionality"}
        )

    geometry_order = ["EPID scaling", "Light vs radiation", "Jaw drive accuracy"]
    geometry_seen = {
        item.label
        for item in items
        if item.category == "Geometry"
    }
    geometry_labels = [label for label in geometry_order if label in geometry_seen]
    if geometry_labels:
        grouped.append(
            PerformedItem(
                category="Geometry",
                label=", ".join(_display_geometry_label(label) for label in geometry_labels),
            )
        )
        handled.update({("Geometry", label) for label in geometry_labels})

    if any(item.category == "EPID Image Quality" for item in items):
        grouped.append(PerformedItem(category="EPID Image Quality", label="Contrast visibility"))
        handled.update({(item.category, item.label) for item in items if item.category == "EPID Image Quality"})

    mlc_labels = {item.label for item in items if item.category == "MLC"}
    if mlc_labels:
        grouped.append(
            PerformedItem(
                category="MLC",
                label=_summarize_mlc_items(mlc_labels),
            )
        )
        handled.update({("MLC", label) for label in mlc_labels})

    for item in items:
        if (item.category, item.label) not in handled:
            grouped.append(item)

    return grouped


def _summarize_catphan_scans(labels: set[str]) -> str:
    expected = {"MFOV CCW", "SFOV CW", "SFOV CCW", "MFOV CW"}
    if expected.issubset(labels):
        return "CatPhan 503 (MFOV+SFOV x CW+CCW)"
    if len(labels) == 1:
        scan = next(iter(labels))
        return f"CatPhan 503 ({scan})"
    return "CatPhan 503 (" + "+".join(sorted(labels)) + ")"


def _display_geometry_label(label: str) -> str:
    if label == "Light vs radiation":
        return "light vs. radiation"
    if label == "Jaw drive accuracy":
        return "jaw drive accuracy"
    return label


def _summarize_mlc_items(labels: set[str]) -> str:
    summary: list[str] = []

    if "Leaf speed constancy" in labels:
        summary.append("Leaf speed constancy")

    if (
        "Sliding window fluence uniformity" in labels
        or "VMAT Dose Rate & Gantry Speed (DRGS) + Dynamic MLC Picket Fence" in labels
    ):
        summary.append("DRGS")

    if any(label.startswith("Picket Fence: ") for label in labels):
        summary.append("Picket fence by gantry angle")

    return ", ".join(summary)

"""Grouping logic for normalized RadMachine records."""

from __future__ import annotations

from dataclasses import asdict

from .models import CandidateEntry, PerformedItem, SourceRecord
from .render import render_candidate


def group_source_records(records: list[SourceRecord]) -> list[CandidateEntry]:
    buckets: dict[tuple[str, str, str], list[SourceRecord]] = {}

    for record in sorted(records, key=_record_sort_key):
        if not record.performed_at or not record.unit:
            continue
        date = record.performed_at[:10]
        entry_type = _infer_entry_type(record)
        group_key = (date, record.unit, _group_label(record, entry_type))
        buckets.setdefault(group_key, []).append(record)

    return [
        _build_candidate(date, unit, label, grouped_records)
        for (date, unit, label), grouped_records in buckets.items()
    ]


def serialize_candidate_entries(entries: list[CandidateEntry]) -> list[dict]:
    serialized: list[dict] = []
    for entry in entries:
        if entry.rendered_org is None:
            entry.rendered_org = render_candidate(entry)
        serialized.append(asdict(entry))
    return serialized


def _record_sort_key(record: SourceRecord) -> tuple[str, str, str]:
    return (
        record.performed_at or "",
        record.unit or "",
        record.title or "",
    )


def _infer_entry_type(record: SourceRecord) -> str:
    equipment = _equipment_group(record)
    frequency = _collection_frequency_name(record)
    if equipment == "linac" and frequency == "monthly":
        return "linac_mqc"
    return "qa_session"


def _equipment_group(record: SourceRecord) -> str | None:
    unit = record.unit or ""
    if unit.startswith("LA"):
        return "linac"
    return None


def _collection_frequency_name(record: SourceRecord) -> str | None:
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


def _group_label(record: SourceRecord, entry_type: str) -> str:
    if entry_type == "linac_mqc":
        return "linac_monthly"
    return record.title or "qa_session"


def _build_candidate(date: str, unit: str, label: str, records: list[SourceRecord]) -> CandidateEntry:
    first = records[0]
    entry_type = _infer_entry_type(first)
    site = first.site

    if entry_type == "linac_mqc":
        title = f"{unit} MQC"
        tags = [tag for tag in (site, unit) if tag]
    else:
        title = first.title or f"{unit} QA"
        tags = [tag for tag in (site, unit) if tag]

    performed_items = [
        PerformedItem(category=_performed_item_category(record), label=_performed_item_label(record))
        for record in records
    ]

    prompts = _notable_prompts(records)

    return CandidateEntry(
        entry_type=entry_type,
        group_key=f"{date}_{unit}_{label}",
        date=date,
        title=title,
        site=site,
        unit=unit,
        tags=tags,
        performed_items=performed_items,
        notable_prompts=prompts,
        source_ids=[f"qa:{record.remote_id}" for record in records],
    )


def _performed_item_category(record: SourceRecord) -> str:
    title = record.title or ""
    return title or "QA"


def _performed_item_label(record: SourceRecord) -> str:
    title = record.title or record.remote_id
    parts = [part.strip() for part in title.split("::")]
    if len(parts) >= 3:
        return " :: ".join(parts[2:])
    if len(parts) == 2:
        return parts[1]
    return title


def _notable_prompts(records: list[SourceRecord]) -> list[str]:
    prompts: list[str] = []
    for record in records:
        session = record.raw.get("session", {})
        for comment in session.get("comments", []):
            text = str(comment.get("comment", "")).strip()
            if text:
                prompts.append(text)
        if record.status == "flagged":
            prompts.append(f"Review flagged results for {record.title}")
    if not prompts:
        prompts.append("Review comments and flagged results")
        prompts.append("Manually enter here")
    else:
        prompts.append("Manually enter here")
    return prompts

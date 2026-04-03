"""Grouping logic for normalized RadMachine records."""

from __future__ import annotations

from dataclasses import asdict

from .models import CandidateEntry, PerformedItem, SourceRecord


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
    return [asdict(entry) for entry in entries]


def _record_sort_key(record: SourceRecord) -> tuple[str, str, str]:
    return (
        record.performed_at or "",
        record.unit or "",
        record.title or "",
    )


def _infer_entry_type(record: SourceRecord) -> str:
    title = (record.title or "").lower()
    if title.startswith("linac monthly ::"):
        return "linac_mqc"
    return "qa_session"


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
        PerformedItem(category=_performed_item_category(record), label=record.title or record.remote_id)
        for record in records
    ]

    return CandidateEntry(
        entry_type=entry_type,
        group_key=f"{date}_{unit}_{label}",
        date=date,
        title=title,
        site=site,
        unit=unit,
        tags=tags,
        performed_items=performed_items,
        notable_prompts=["Review comments and flagged results"],
        source_ids=[f"qa:{record.remote_id}" for record in records],
    )


def _performed_item_category(record: SourceRecord) -> str:
    title = record.title or ""
    if "::" in title:
        return title.split("::", 1)[1].strip().split("::", 1)[0].strip()
    return "QA"

"""Grouping logic for normalized RadMachine records."""

from __future__ import annotations

from dataclasses import asdict

from .models import CandidateEntry, PerformedItem, SourceRecord
from .render import render_candidate
from .site_rules import (
    aggregate_performed_items,
    additional_notable_prompts,
    collection_frequency_name,
    equipment_group,
    map_performed_item,
    resolve_entry_type,
)


def group_source_records(records: list[SourceRecord]) -> list[CandidateEntry]:
    monthly_bucket_keys = {
        (record.performed_at[:10], record.unit)
        for record in records
        if record.performed_at
        and record.unit
        and _infer_entry_type(record) == "linac_mqc"
    }
    buckets: dict[tuple[str, str, str], list[SourceRecord]] = {}

    for record in sorted(records, key=_record_sort_key):
        if not record.performed_at or not record.unit:
            continue
        date = record.performed_at[:10]
        entry_type = _infer_entry_type(record)
        group_key = (date, record.unit, _group_label(record, entry_type, monthly_bucket_keys))
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
    equipment = equipment_group(record)
    frequency = collection_frequency_name(record)
    if equipment == "linac" and frequency == "monthly":
        return "linac_mqc"
    if (record.title or "") == "ABC Weekly QC":
        return "abc_weekly"
    return "qa_session"


def _group_label(
    record: SourceRecord,
    entry_type: str,
    monthly_bucket_keys: set[tuple[str, str]],
) -> str:
    if entry_type == "linac_mqc":
        return "linac_monthly"
    if entry_type == "abc_weekly":
        return "abc_weekly"
    if (
        equipment_group(record) == "linac"
        and (record.title or "").startswith("Reference dosimetry :: ")
        and record.performed_at
        and (record.performed_at[:10], record.unit or "") in monthly_bucket_keys
    ):
        return "linac_monthly"
    return record.title or "qa_session"


def _build_candidate(date: str, unit: str, label: str, records: list[SourceRecord]) -> CandidateEntry:
    first = records[0]
    entry_type = resolve_entry_type(_infer_entry_type(first), records)
    site = first.site

    if entry_type == "linac_mqc":
        title = f"{unit} MQC"
        tags = [tag for tag in (site, unit) if tag]
        group_label = label
    elif entry_type == "post_pmi":
        title = f"{unit} post-PMI"
        tags = [tag for tag in (site, unit) if tag]
        group_label = "post_pmi"
    elif entry_type == "abc_weekly":
        title = f"{unit} Weekly QA"
        tags = [tag for tag in (site, unit) if tag]
        group_label = "abc_weekly"
    else:
        title = first.title or f"{unit} QA"
        tags = [tag for tag in (site, unit) if tag]
        group_label = label

    performed_items = aggregate_performed_items(
        entry_type,
        [map_performed_item(record, entry_type) for record in records],
    )

    prompts = additional_notable_prompts(entry_type, records) + _notable_prompts(records, entry_type)

    return CandidateEntry(
        entry_type=entry_type,
        group_key=f"{date}_{unit}_{group_label}",
        date=date,
        title=title,
        site=site,
        unit=unit,
        tags=tags,
        performed_items=performed_items,
        notable_prompts=prompts,
        source_ids=[f"qa:{record.remote_id}" for record in records],
    )


def _notable_prompts(records: list[SourceRecord], entry_type: str) -> list[str]:
    prompts: list[str] = []
    for record in records:
        session = record.raw.get("session", {})
        item = map_performed_item(record, entry_type)
        prompt_label = item.label if item.category in {"Dosimetry", "MLC"} else record.title or item.label
        for comment in session.get("comments", []):
            text = str(comment.get("comment", "")).strip()
            if text:
                prompts.append(f"{prompt_label}\n  - {text}")
        if record.status == "flagged":
            prompts.append(f"{prompt_label}\n  - Review flagged results")
    if not prompts:
        prompts.append("Review comments and flagged results")
    return prompts

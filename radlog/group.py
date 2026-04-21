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
        bucket_unit = _bucket_unit(record, entry_type)
        group_key = (date, bucket_unit, _group_label(record, entry_type, monthly_bucket_keys))
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
    if record.source_type == "service_event":
        equipment = equipment_group(record)
        if equipment == "abc":
            return "abc_ad_hoc"
        if equipment == "linac":
            return "linac_ad_hoc"
        return "ad_hoc_qa"

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
    if entry_type == "abc_ad_hoc":
        return "abc_ad_hoc"
    if entry_type == "linac_ad_hoc":
        return "linac_ad_hoc"
    if entry_type == "ad_hoc_qa":
        return "ad_hoc_qa"
    if (
        equipment_group(record) == "linac"
        and (record.title or "").startswith("Reference dosimetry :: ")
        and record.performed_at
        and (record.performed_at[:10], record.unit or "") in monthly_bucket_keys
    ):
        return "linac_monthly"
    return record.title or "qa_session"


def _bucket_unit(record: SourceRecord, entry_type: str) -> str:
    if entry_type == "abc_weekly":
        return "ABC"
    if entry_type == "abc_ad_hoc":
        return "ABC"
    return record.unit or ""


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
        title = "ABC Weekly"
        tags = ["ABCWeekly"]
        group_label = "abc_weekly"
        unit = "ABC"
    elif entry_type == "abc_ad_hoc":
        title = "ABC Ad hoc QA"
        tags = [_compact_tag(first.unit)]
        group_label = "abc_ad_hoc"
        unit = "ABC"
    elif entry_type == "linac_ad_hoc":
        title = f"{unit} Ad hoc QA"
        tags = [tag for tag in (site, unit, "AdHocQA") if tag]
        group_label = "linac_ad_hoc"
    elif entry_type == "ad_hoc_qa":
        title = f"{unit} Ad hoc QA"
        tags = [tag for tag in (site, unit, "AdHocQA") if tag]
        group_label = "ad_hoc_qa"
    else:
        title = first.title or f"{unit} QA"
        tags = [tag for tag in (site, unit) if tag]
        group_label = label

    metadata = _record_urls_metadata(records, entry_type)
    if entry_type in {"abc_ad_hoc", "linac_ad_hoc", "ad_hoc_qa"}:
        performed_items = _service_event_performed_items(records)
        prompts = _service_event_detail_prompts(records)
        metadata.update(_service_event_metadata(records))
    else:
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
        source_ids=[f"{_source_prefix(record)}:{record.remote_id}" for record in records],
        metadata=metadata,
    )


def _notable_prompts(records: list[SourceRecord], entry_type: str) -> list[str]:
    if entry_type in {"abc_ad_hoc", "linac_ad_hoc", "ad_hoc_qa"}:
        prompts = []
        for record in records:
            service_event = record.raw.get("service_event", {})
            if not isinstance(service_event, dict):
                continue
            work_description = str(service_event.get("work_description", "")).strip()
            if work_description:
                prompts.append(work_description)
        if prompts:
            return prompts
        return ["<no work description in source record>"]

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
        prompts.append("<none in source records>")
    return prompts


def _source_prefix(record: SourceRecord) -> str:
    if record.source_type == "service_event":
        return "service"
    return "qa"


def _service_event_performed_items(records: list[SourceRecord]) -> list[PerformedItem]:
    items: list[PerformedItem] = []
    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        problem_description = str(service_event.get("problem_description", "")).strip()
        work_description = str(service_event.get("work_description", "")).strip()
        work_summary, _ = _split_service_work_description(work_description)

        if problem_description:
            items.append(PerformedItem(category="Problem Description", label=problem_description))
        if work_summary:
            items.append(PerformedItem(category="Work description", label=work_summary))

    return items


def _service_event_detail_prompts(records: list[SourceRecord]) -> list[str]:
    prompts: list[str] = []
    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        work_description = str(service_event.get("work_description", "")).strip()
        _, detail = _split_service_work_description(work_description)
        if detail:
            prompts.append(detail)
    return prompts


def _service_event_metadata(records: list[SourceRecord]) -> dict[str, object]:
    return_to_service_qa: list[str] = []

    for record in records:
        service_event = record.raw.get("service_event", {})
        if not isinstance(service_event, dict):
            continue

        for qa_name in service_event.get("return_to_service_qa", []):
            normalized = str(qa_name).strip()
            if normalized and normalized not in return_to_service_qa:
                return_to_service_qa.append(normalized)

    metadata: dict[str, object] = {}
    if return_to_service_qa:
        metadata["return_to_service_qa"] = return_to_service_qa
    return metadata


def _split_service_work_description(work_description: str) -> tuple[str, str]:
    normalized = work_description.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return "", ""

    parts = normalized.split("\n\n", 1)
    summary = parts[0].strip()
    detail = parts[1].strip() if len(parts) > 1 else ""
    return summary, detail


def _record_urls_metadata(records: list[SourceRecord], entry_type: str) -> dict[str, object]:
    urls: list[str] = []
    for record in records:
        url = _record_url(record)
        if url and url not in urls:
            urls.append(url)

    metadata: dict[str, object] = {}
    if entry_type == "linac_mqc":
        metadata["suppress_links_block"] = True
    if len(urls) == 1:
        metadata["url"] = urls[0]
    elif urls and entry_type != "linac_mqc":
        metadata["urls"] = urls
    return metadata


def _record_url(record: SourceRecord) -> str | None:
    if record.source_type == "service_event":
        service_event = record.raw.get("service_event", {})
        if isinstance(service_event, dict):
            url = str(service_event.get("event_url", "")).strip()
            return url or None
        return None

    session = record.raw.get("session", {})
    if isinstance(session, dict):
        url = str(session.get("site_url", "")).strip()
        if url:
            return url
    return None


def _compact_tag(value: str | None) -> str:
    if not value:
        return ""
    return value.replace(" ", "")

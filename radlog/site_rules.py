"""Default grouping rules with no site-specific policy."""

from __future__ import annotations

from typing import Any

from .models import CandidateEntry, PerformedItem, SourceRecord


class SiteRules:
    """Conservative default rules for source-record grouping.

    Real logbook workflows should usually provide their own rules object via
    `[grouping].rules`.
    """

    def prepare(self, records: list[SourceRecord]) -> Any:
        return None

    def include_record(self, record: SourceRecord, context: Any) -> bool:
        return bool(record.performed_at and record.unit)

    def record_sort_key(self, record: SourceRecord) -> tuple[str, str, str]:
        return (
            record.performed_at or "",
            record.unit or "",
            record.title or "",
        )

    def bucket_key(self, record: SourceRecord, context: Any) -> tuple[str, str, str]:
        if not record.performed_at or not record.unit:
            raise ValueError("Cannot bucket a record without performed_at and unit")
        return (
            record.performed_at[:10],
            record.unit,
            record.title or record.source_type,
        )

    def build_candidate(
        self,
        bucket_key: tuple[str, str, str],
        records: list[SourceRecord],
        context: Any,
    ) -> CandidateEntry:
        date, unit, label = bucket_key
        first = records[0]
        site = first.site
        title = first.title or label

        return CandidateEntry(
            entry_type=first.source_type,
            group_key=f"{date}_{unit}_{_compact_key(label)}",
            date=date,
            title=title,
            site=site,
            unit=unit,
            tags=[tag for tag in (site, unit) if tag],
            performed_items=[
                PerformedItem(category=record.source_type, label=record.title or record.remote_id)
                for record in records
            ],
            source_ids=[f"{record.source_type}:{record.remote_id}" for record in records],
        )


def _compact_key(value: str) -> str:
    return "_".join(value.lower().split())


DEFAULT_RULES = SiteRules()

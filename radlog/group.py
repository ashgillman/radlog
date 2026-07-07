"""Generic grouping orchestration for normalized RadMachine records."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from .models import CandidateEntry, SourceRecord
from .site_rules import DEFAULT_RULES


class GroupingRules(Protocol):
    """Protocol implemented by project or user grouping rules."""

    def prepare(self, records: list[SourceRecord]) -> Any: ...

    def include_record(self, record: SourceRecord, context: Any) -> bool: ...

    def record_sort_key(self, record: SourceRecord) -> tuple[str, str, str]: ...

    def bucket_key(self, record: SourceRecord, context: Any) -> tuple[str, str, str]: ...

    def build_candidate(
        self,
        bucket_key: tuple[str, str, str],
        records: list[SourceRecord],
        context: Any,
    ) -> CandidateEntry: ...


def group_source_records(
    records: list[SourceRecord],
    *,
    rules: GroupingRules = DEFAULT_RULES,
) -> list[CandidateEntry]:
    """Group normalized records into candidate entries using RULES."""
    context = rules.prepare(records)
    buckets: dict[tuple[str, str, str], list[SourceRecord]] = {}

    for record in sorted(records, key=rules.record_sort_key):
        if not rules.include_record(record, context):
            continue
        buckets.setdefault(rules.bucket_key(record, context), []).append(record)

    return [
        rules.build_candidate(bucket_key, grouped_records, context)
        for bucket_key, grouped_records in buckets.items()
    ]


def serialize_candidate_entries(entries: list[CandidateEntry]) -> list[dict]:
    return [asdict(entry) for entry in entries]

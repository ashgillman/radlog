"""Models for factual RadMachine QA reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QaIssue:
    session_id: str
    session_url: str | None
    performed_at: str | None
    equipment_name: str | None
    equipment_group: str | None
    collection_name: str | None
    test_label: str | None
    issue_type: str
    severity: str | None
    value: Any
    pass_fail: str | bool | None
    comment: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AbnormalQaReport:
    start: str
    end: str
    issues: list[QaIssue] = field(default_factory=list)


@dataclass(slots=True)
class ReportCollectionProfile:
    sessions_seen: int = 0
    sessions_in_range: int = 0
    sessions_with_issues: int = 0
    metadata_fetches: int = 0
    metadata_cache_hits: int = 0
    metadata_fetches_by_kind: dict[str, int] = field(default_factory=dict)
    test_lists_flattened: int = 0
    seconds_paginating: float = 0.0
    seconds_metadata: float = 0.0
    seconds_flattening: float = 0.0


@dataclass(slots=True)
class TestDefinition:
    label: str
    slug: str | None
    url: str | None
    raw: dict[str, Any] = field(default_factory=dict)

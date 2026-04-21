"""Normalized models used throughout the importer pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PerformedItem:
    category: str
    label: str
    duration_min: int | None = None
    url: str | None = None
    links: list["LinkRef"] = field(default_factory=list)


@dataclass(slots=True)
class LinkRef:
    label: str
    url: str


@dataclass(slots=True)
class FlaggedItem:
    severity: str
    category: str
    label: str
    detail: str


@dataclass(slots=True)
class SourceRecord:
    source_type: str
    remote_id: str
    created_at: str | None = None
    updated_at: str | None = None
    performed_at: str | None = None
    created_by: str | None = None
    unit: str | None = None
    site: str | None = None
    title: str | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateEntry:
    entry_type: str
    group_key: str
    date: str
    title: str
    site: str | None = None
    unit: str | None = None
    tags: list[str] = field(default_factory=list)
    performed_items: list[PerformedItem] = field(default_factory=list)
    flagged_items: list[FlaggedItem] = field(default_factory=list)
    notable_prompts: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    rendered_org: str | None = None

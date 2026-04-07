"""Render candidate entries as draft Org text."""

from __future__ import annotations

from datetime import date

from .models import CandidateEntry, PerformedItem


def render_candidate(entry: CandidateEntry) -> str:
    renderer = RENDERERS.get(entry.entry_type, render_generic_qa)
    return renderer(entry)


def render_linac_mqc(entry: CandidateEntry) -> str:
    lines = [
        f"**** [{_org_date(entry.date)}] {entry.title} {_render_tags(entry.tags)}".rstrip(),
        ":PROPERTIES:",
        f":RM_GROUP_KEY: {entry.group_key}",
        f":RM_SOURCE_IDS: {','.join(entry.source_ids)}",
        ":END:",
        "Performed as rostered duty:",
    ]

    for item in entry.performed_items:
        lines.append(f"- {item.category} :: {item.label}")

    lines.extend(
        [
            "",
            "Notable events:",
        ]
    )

    if entry.notable_prompts:
        for prompt in entry.notable_prompts:
            lines.append(f"- {prompt}")
    else:
        lines.append("- Manually enter here")

    return "\n".join(lines)


def render_post_pmi(entry: CandidateEntry) -> str:
    rts_items, extra_items = _partition_post_pmi_items(entry)

    lines = [
        f"**** [{_org_date(entry.date)}] {entry.title} {_render_tags(entry.tags)}".rstrip(),
        ":PROPERTIES:",
        f":RM_GROUP_KEY: {entry.group_key}",
        f":RM_SOURCE_IDS: {','.join(entry.source_ids)}",
        ":END:",
        "Maintenance:",
        "- Beam tuning",
        "",
        "Return to service:",
    ]

    for item in rts_items:
        lines.append(f"- {item.category} :: {item.label}")

    lines.extend(
        [
            "",
            "Additional MQA:",
        ]
    )

    for item in extra_items:
        lines.append(f"- {item.category} :: {item.label}")

    lines.extend(
        [
            "",
            "Notable events:",
        ]
    )

    if entry.notable_prompts:
        for prompt in entry.notable_prompts:
            lines.append(f"- {prompt}")
    else:
        lines.append("- Manually enter here")

    return "\n".join(lines)


def render_generic_qa(entry: CandidateEntry) -> str:
    lines = [
        f"**** [{_org_date(entry.date)}] {entry.title} {_render_tags(entry.tags)}".rstrip(),
        ":PROPERTIES:",
        f":RM_GROUP_KEY: {entry.group_key}",
        f":RM_SOURCE_IDS: {','.join(entry.source_ids)}",
        ":END:",
        "Performed:",
    ]
    for item in entry.performed_items:
        lines.append(f"- {item.label}")
    return "\n".join(lines)


def _org_date(date_text: str) -> str:
    parsed = date.fromisoformat(date_text)
    return parsed.strftime("%Y-%m-%d %a")


def _render_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    return ":" + ":".join(tags) + ":"


def _partition_post_pmi_items(entry: CandidateEntry) -> tuple[list[PerformedItem], list[PerformedItem]]:
    rts_items = [
        item
        for item in entry.performed_items
        if item.category == "Dosimetry" and item.label != "Quickcheck Constancy"
    ]
    extra_items = [
        item
        for item in entry.performed_items
        if item not in rts_items
    ]
    return rts_items, extra_items


RENDERERS = {
    "linac_mqc": render_linac_mqc,
    "post_pmi": render_post_pmi,
}

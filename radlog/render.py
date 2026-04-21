"""Render candidate entries as draft Org text."""

from __future__ import annotations

from datetime import date

from .models import CandidateEntry, LinkRef, PerformedItem


def render_candidate(entry: CandidateEntry) -> str:
    renderer = RENDERERS.get(entry.entry_type, render_generic_qa)
    return renderer(entry)


def render_linac_mqc(entry: CandidateEntry) -> str:
    rostered_items = [item for item in entry.performed_items if item.category != "Ad hoc"]
    ad_hoc_items = [item for item in entry.performed_items if item.category == "Ad hoc"]

    lines = _render_entry_header(entry)
    lines.append("Performed as rostered duty:")

    for item in rostered_items:
        lines.extend(_render_performed_item(item, category=item.category))

    if ad_hoc_items:
        lines.extend(
            [
                "",
                "Ad hoc:",
            ]
        )
        for item in ad_hoc_items:
            lines.extend(_render_performed_item(item, category=None))

    lines.extend(
        [
            "",
            "Notable events:",
        ]
    )

    if entry.notable_prompts:
        for prompt in entry.notable_prompts:
            lines.extend(_render_notable_prompt(prompt))

    return "\n".join(lines)


def render_post_pmi(entry: CandidateEntry) -> str:
    rts_items, extra_items, ad_hoc_items = _partition_post_pmi_items(entry)

    lines = _render_entry_header(entry)
    lines.extend(
        [
            "Maintenance:",
            "- Beam tuning",
            "",
            "Return to service:",
        ]
    )

    for item in rts_items:
        lines.extend(_render_performed_item(item, category=item.category))

    lines.extend(
        [
            "",
            "Additional MQA:",
        ]
    )

    for item in extra_items:
        lines.extend(_render_performed_item(item, category=item.category))

    if ad_hoc_items:
        lines.extend(
            [
                "",
                "Ad hoc:",
            ]
        )
        for item in ad_hoc_items:
            lines.extend(_render_performed_item(item, category=None))

    lines.extend(
        [
            "",
            "Notable events:",
        ]
    )

    if entry.notable_prompts:
        for prompt in entry.notable_prompts:
            lines.extend(_render_notable_prompt(prompt))

    return "\n".join(lines)


def render_generic_qa(entry: CandidateEntry) -> str:
    lines = _render_entry_header(entry)
    lines.append("Performed:")
    for item in entry.performed_items:
        if item.category == "QA":
            lines.extend(_render_performed_item(item, category=None))
        else:
            lines.extend(_render_performed_item(item, category=item.category))

    if entry.notable_prompts:
        lines.extend(
            [
                "",
                "Notable events:",
            ]
        )
        for prompt in entry.notable_prompts:
            lines.extend(_render_notable_prompt(prompt))

    return "\n".join(lines)


def render_service_ad_hoc(entry: CandidateEntry) -> str:
    lines = _render_entry_header(entry)

    for index, item in enumerate(entry.performed_items):
        lines.extend(_render_performed_item(item, category=item.category))
        if item.category == "Work description" and entry.notable_prompts:
            for prompt in entry.notable_prompts:
                lines.append("")
                lines.extend(_render_indented_paragraph(prompt))
        elif index != len(entry.performed_items) - 1:
            continue

    return_to_service_qa = entry.metadata.get("return_to_service_qa", [])
    if isinstance(return_to_service_qa, list) and return_to_service_qa:
        lines.append("- Return To Service QA ::")
        for qa_name in return_to_service_qa:
            lines.append(f"  - {qa_name}")

    return "\n".join(lines)


def _org_date(date_text: str) -> str:
    parsed = date.fromisoformat(date_text)
    return parsed.strftime("%Y-%m-%d %a")


def _render_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    return ":" + ":".join(tags) + ":"


def _render_notable_prompt(prompt: str) -> list[str]:
    normalized = prompt.replace("\r\n", "\n").replace("\r", "\n")
    parts = normalized.split("\n")
    if not parts:
        return []

    lines = [f"- {parts[0]}"]
    for part in parts[1:]:
        if not part:
            lines.append("  ")
        elif part.startswith("  "):
            lines.append(part)
        else:
            lines.append(f"  {part.lstrip()}")
    return lines


def _render_entry_header(entry: CandidateEntry) -> list[str]:
    lines = [
        f"**** [{_org_date(entry.date)}] {entry.title} {_render_tags(entry.tags)}".rstrip(),
        ":PROPERTIES:",
        f":RM_GROUP_KEY: {entry.group_key}",
        f":RM_SOURCE_IDS: {','.join(entry.source_ids)}",
    ]

    url = str(entry.metadata.get("url", "")).strip()
    if url:
        lines.append(f":URL: {url}")

    lines.append(":END:")
    lines.extend(_render_links_block(entry))
    return lines


def _render_links_block(entry: CandidateEntry) -> list[str]:
    if entry.metadata.get("suppress_links_block"):
        return []
    urls = entry.metadata.get("urls", [])
    if not isinstance(urls, list) or not urls:
        return []

    lines = ["RadMachine links:"]
    for url in urls:
        lines.append(f"- {url}")
    lines.append("")
    return lines


def _render_indented_paragraph(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for part in normalized.split("\n"):
        if not part:
            lines.append("  ")
        else:
            lines.append(f"  {part.lstrip()}")
    return lines


def _render_item(
    category: str | None,
    label: str,
    url: str | None,
    links: list[LinkRef],
) -> list[str]:
    rendered_label = _render_item_label(label, url, links)
    normalized = rendered_label.replace("\r\n", "\n").replace("\r", "\n")
    parts = normalized.split("\n")
    if category:
        lines = [f"- {category} :: {parts[0]}"]
    else:
        lines = [f"- {parts[0]}"]

    for part in parts[1:]:
        if not part:
            lines.append("  ")
        else:
            lines.append(f"  {part.lstrip()}")
    return lines


def _render_performed_item(item: PerformedItem, *, category: str | None) -> list[str]:
    return _render_item(category, item.label, item.url, item.links)


def _render_item_label(label: str, url: str | None, links: list[LinkRef]) -> str:
    if links:
        rendered_links = ", ".join(_render_org_link(link) for link in links)
        return f"{label} ({rendered_links})"
    if url:
        return f"[[{url}][{label}]]"
    return label


def _render_org_link(link: LinkRef) -> str:
    return f"[[{link.url}][{link.label}]]"


def _partition_post_pmi_items(entry: CandidateEntry) -> tuple[list[PerformedItem], list[PerformedItem], list[PerformedItem]]:
    rts_items = [
        item
        for item in entry.performed_items
        if item.category == "Dosimetry" and item.label != "Quickcheck Constancy"
    ]
    ad_hoc_items = [item for item in entry.performed_items if item.category == "Ad hoc"]
    extra_items = [
        item
        for item in entry.performed_items
        if item not in rts_items and item not in ad_hoc_items
    ]
    return rts_items, extra_items, ad_hoc_items


RENDERERS = {
    "abc_ad_hoc": render_service_ad_hoc,
    "abc_weekly": render_generic_qa,
    "ad_hoc_qa": render_service_ad_hoc,
    "linac_mqc": render_linac_mqc,
    "linac_ad_hoc": render_service_ad_hoc,
    "post_pmi": render_post_pmi,
}

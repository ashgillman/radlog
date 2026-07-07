"""Render candidate entries as generic Org logbook text."""

from __future__ import annotations

from datetime import date

from ..models import CandidateEntry, LinkRef, PerformedItem


def render_candidate(entry: CandidateEntry) -> str:
    return render_generic(entry)


def render_generic(entry: CandidateEntry) -> str:
    lines = _render_entry_header(entry)
    lines.append("Performed:")
    for item in entry.performed_items:
        if item.category in {"QA", entry.entry_type}:
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

    lines = ["#+begin_comment", "RadMachine links:"]
    for url in urls:
        lines.append(f"- {url}")
    lines.extend(["#+end_comment", ""])
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


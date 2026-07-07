"""Example authored Org logbook renderer.

Point `[render].logbook_org_renderer` at `render_ag_org:render_candidate` with
`./examples` in `[extensions].paths`, then customize the function bodies here
or copy this module into a personal radlog extensions directory.
"""

from __future__ import annotations

from radlog.models import CandidateEntry, PerformedItem
from radlog.renderers.logbook_org import (
    _render_entry_header,
    _render_indented_paragraph,
    _render_notable_prompt,
    _render_performed_item,
    render_generic,
)


def render_candidate(entry: CandidateEntry) -> str:
    renderer = RENDERERS.get(entry.entry_type, render_generic)
    return renderer(entry)


def render_linac_mqc(entry: CandidateEntry) -> str:
    rostered_items = [item for item in entry.performed_items if item.category != "Ad hoc"]
    ad_hoc_items = [item for item in entry.performed_items if item.category == "Ad hoc"]

    lines = _render_entry_header(entry)
    lines.append("Performed as rostered duty:")

    for item in rostered_items:
        lines.extend(_render_performed_item(item, category=item.category))

    if ad_hoc_items:
        lines.extend(["", "Ad hoc:"])
        for item in ad_hoc_items:
            lines.extend(_render_performed_item(item, category=None))

    lines.extend(["", "Notable events:"])

    if entry.notable_prompts:
        for prompt in entry.notable_prompts:
            lines.extend(_render_notable_prompt(prompt))

    return "\n".join(lines)


def render_post_pmi(entry: CandidateEntry) -> str:
    rts_items, extra_items, ad_hoc_items = _partition_post_pmi_items(entry)
    rts_prompts, notable_prompts = _partition_post_pmi_prompts(entry.notable_prompts)

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

    for prompt in rts_prompts:
        lines.append(f"- {prompt}")

    lines.extend(["", "Additional MQA:"])

    for item in extra_items:
        lines.extend(_render_performed_item(item, category=item.category))

    if ad_hoc_items:
        lines.extend(["", "Ad hoc:"])
        for item in ad_hoc_items:
            lines.extend(_render_performed_item(item, category=None))

    lines.extend(["", "Notable events:"])

    if notable_prompts:
        for prompt in notable_prompts:
            lines.extend(_render_notable_prompt(prompt))

    return "\n".join(lines)


def render_service_ad_hoc(entry: CandidateEntry) -> str:
    lines = _render_entry_header(entry)

    for item in entry.performed_items:
        lines.extend(_render_performed_item(item, category=item.category))
        if item.category == "Work description" and entry.notable_prompts:
            for prompt in entry.notable_prompts:
                lines.append("")
                lines.extend(_render_indented_paragraph(prompt))

    return_to_service_qa = entry.metadata.get("return_to_service_qa", [])
    if isinstance(return_to_service_qa, list) and return_to_service_qa:
        lines.append("- Return To Service QA ::")
        for qa_name in return_to_service_qa:
            lines.append(f"  - {qa_name}")

    return "\n".join(lines)


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


def _partition_post_pmi_prompts(prompts: list[str]) -> tuple[list[str], list[str]]:
    rts_prompt = "Linac ready for clinical use. Re-enable energies and document on MOSAIQ."
    rts_prompts = [prompt for prompt in prompts if prompt == rts_prompt]
    notable_prompts = [prompt for prompt in prompts if prompt != rts_prompt]
    return rts_prompts, notable_prompts


RENDERERS = {
    "abc_ad_hoc": render_service_ad_hoc,
    "abc_weekly": render_generic,
    "ad_hoc_qa": render_service_ad_hoc,
    "linac_mqc": render_linac_mqc,
    "linac_ad_hoc": render_service_ad_hoc,
    "post_pmi": render_post_pmi,
}

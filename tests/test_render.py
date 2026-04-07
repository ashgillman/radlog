from __future__ import annotations

from radlog.models import CandidateEntry, PerformedItem
from radlog.render import render_candidate


def test_render_linac_mqc_org_text() -> None:
    entry = CandidateEntry(
        entry_type="linac_mqc",
        group_key="2026-03-06_LA7_linac_monthly",
        date="2026-03-06",
        title="LA7 MQC",
        site="Hayman",
        unit="LA7",
        tags=["Hayman", "LA7"],
        performed_items=[
            PerformedItem(category="Dosimetry", label="Output and relative dosimetry :: 10 MV"),
            PerformedItem(category="Dosimetry", label="Output and relative dosimetry :: 6 MV"),
        ],
        notable_prompts=["Output verification/re-baselining", "Manually enter here"],
        source_ids=["qa:13162", "qa:13167"],
    )

    rendered = render_candidate(entry)

    assert "**** [2026-03-06 Fri] LA7 MQC :Hayman:LA7:" in rendered
    assert ":RM_GROUP_KEY: 2026-03-06_LA7_linac_monthly" in rendered
    assert ":RM_SOURCE_IDS: qa:13162,qa:13167" in rendered
    assert "- Dosimetry :: Output and relative dosimetry :: 10 MV" in rendered
    assert "- Output verification/re-baselining" in rendered


def test_render_post_pmi_org_text() -> None:
    entry = CandidateEntry(
        entry_type="post_pmi",
        group_key="2026-03-06_LA7_post_pmi",
        date="2026-03-06",
        title="LA7 post-PMI",
        site="Hayman",
        unit="LA7",
        tags=["Hayman", "LA7"],
        performed_items=[
            PerformedItem(category="Dosimetry", label="Output and relative dosimetry :: 10 MV"),
            PerformedItem(category="Dosimetry", label="Photon profile constancy"),
        ],
        notable_prompts=[
            "Photon profile constancy\n  - Discussed results with AB.",
            "Picket Fence: Gantry 270 Panel to G\n  - Peripheral leaf flagging tol, not clinically of high relevance",
        ],
        source_ids=["qa:13162", "qa:13169"],
    )

    rendered = render_candidate(entry)

    assert "**** [2026-03-06 Fri] LA7 post-PMI :Hayman:LA7:" in rendered
    assert ":RM_GROUP_KEY: 2026-03-06_LA7_post_pmi" in rendered
    assert "- Photon profile constancy" in rendered
    assert "  - Discussed results with AB." in rendered

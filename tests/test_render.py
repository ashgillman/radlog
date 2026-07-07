from __future__ import annotations

from examples.render_ag_org import render_candidate
from radlog.models import CandidateEntry, LinkRef, PerformedItem
from radlog.renderers.logbook_org import render_candidate as render_generic_org_candidate


def test_render_generic_org_text() -> None:
    entry = CandidateEntry(
        entry_type="qa_session",
        group_key="2026-03-06_LAx_daily_qa",
        date="2026-03-06",
        title="Daily QA",
        site="LinacName",
        unit="LAx",
        tags=["LinacName", "LAx"],
        performed_items=[
            PerformedItem(category="qa_session", label="Daily QA"),
            PerformedItem(category="Comment", label="Output noted"),
        ],
        notable_prompts=["Review comment"],
        source_ids=["qa_session:1"],
    )

    rendered = render_generic_org_candidate(entry)

    assert "**** [2026-03-06 Fri] Daily QA :LinacName:LAx:" in rendered
    assert "- Daily QA" in rendered
    assert "- Comment :: Output noted" in rendered
    assert "- Review comment" in rendered


def test_render_linac_mqc_org_text() -> None:
    entry = CandidateEntry(
        entry_type="linac_mqc",
        group_key="2026-03-06_LAx_linac_monthly",
        date="2026-03-06",
        title="LAx MQC",
        site="LinacName",
        unit="LAx",
        tags=["LinacName", "LAx"],
        performed_items=[
            PerformedItem(
                category="Imaging",
                label="CatPhan 503",
                links=[
                    LinkRef(label="MFOV CCW", url="https://radmachine.example/demo-customer/qa/session/details/13805/"),
                    LinkRef(label="MFOV CWA", url="https://radmachine.example/demo-customer/qa/session/details/13806/"),
                    LinkRef(label="SFOV CCW", url="https://radmachine.example/demo-customer/qa/session/details/13807/"),
                    LinkRef(label="SFOV CW", url="https://radmachine.example/demo-customer/qa/session/details/13808/"),
                ],
            ),
            PerformedItem(
                category="Winston Lutz",
                label="6 MV",
                url="https://radmachine.example/demo-customer/qa/session/details/13809/",
            ),
        ],
        notable_prompts=["<none in source records>"],
        source_ids=["qa:13805", "qa:13806", "qa:13807", "qa:13808", "qa:13809"],
        metadata={"suppress_links_block": True},
    )

    rendered = render_candidate(entry)

    assert "**** [2026-03-06 Fri] LAx MQC :LinacName:LAx:" in rendered
    assert ":RM_GROUP_KEY: 2026-03-06_LAx_linac_monthly" in rendered
    assert ":RM_SOURCE_IDS: qa:13805,qa:13806,qa:13807,qa:13808,qa:13809" in rendered
    assert "RadMachine links:" not in rendered
    assert "- Imaging :: CatPhan 503 ([[https://radmachine.example/demo-customer/qa/session/details/13805/][MFOV CCW]], [[https://radmachine.example/demo-customer/qa/session/details/13806/][MFOV CWA]], [[https://radmachine.example/demo-customer/qa/session/details/13807/][SFOV CCW]], [[https://radmachine.example/demo-customer/qa/session/details/13808/][SFOV CW]])" in rendered
    assert "- Winston Lutz :: [[https://radmachine.example/demo-customer/qa/session/details/13809/][6 MV]]" in rendered
    assert "- <none in source records>" in rendered
    assert "Manually enter here" not in rendered


def test_render_post_pmi_org_text() -> None:
    entry = CandidateEntry(
        entry_type="post_pmi",
        group_key="2026-03-06_LAx_post_pmi",
        date="2026-03-06",
        title="LAx post-PMI",
        site="LinacName",
        unit="LAx",
        tags=["LinacName", "LAx"],
        performed_items=[
            PerformedItem(
                category="Dosimetry",
                label="Photon and electron profile, output and energy constancy, all energies",
            ),
            PerformedItem(category="Dosimetry", label="Quickcheck Constancy"),
            PerformedItem(category="Safety and Functionality", label="Mechanical drive and interlocks"),
        ],
        notable_prompts=[
            "Linac ready for clinical use. Re-enable energies and document on MOSAIQ.",
            "Photon profile constancy\r\n  - Discussed results with AB.",
            "Reference dosimetry :: Photons :: 10 MV\r\n  - 10 MV output has been low. Acquire output in water to validate SW.\r\n- SW output: -0.76%\r\n- QC output: -0.15%\r\n- Water output: -0.75%\r\n\r\nOutput is actually drifting month-to-month. Within tolerance now, no update to linac outputs.",
            "Picket Fence: Gantry 270 Panel to G\r\n  - Peripheral leaf flagging tol, not clinically of high relevance",
        ],
        source_ids=["qa:13162", "qa:13169"],
        metadata={
            "urls": [
                "https://radmachine.example/demo-customer/qa/session/details/13162/",
                "https://radmachine.example/demo-customer/qa/session/details/13169/",
            ]
        },
    )

    rendered = render_candidate(entry)

    assert "**** [2026-03-06 Fri] LAx post-PMI :LinacName:LAx:" in rendered
    assert ":RM_GROUP_KEY: 2026-03-06_LAx_post_pmi" in rendered
    assert "#+begin_comment" in rendered
    assert "RadMachine links:" in rendered
    assert "- https://radmachine.example/demo-customer/qa/session/details/13162/" in rendered
    assert "#+end_comment" in rendered
    assert "Maintenance:" in rendered
    assert "- Beam tuning" in rendered
    assert "Return to service:" in rendered
    assert "- Dosimetry :: Photon and electron profile, output and energy constancy, all energies" in rendered
    assert "- Linac ready for clinical use. Re-enable energies and document on MOSAIQ." in rendered
    assert "Additional MQA:" in rendered
    assert "- Dosimetry :: Quickcheck Constancy" in rendered
    assert "- Safety and Functionality :: Mechanical drive and interlocks" in rendered
    assert "- Photon profile constancy" in rendered
    assert "  - Discussed results with AB." in rendered
    assert "\r" not in rendered
    assert "- Reference dosimetry :: Photons :: 10 MV" in rendered
    assert "  - SW output: -0.76%" in rendered
    assert "  - QC output: -0.15%" in rendered
    assert "  Output is actually drifting month-to-month. Within tolerance now, no update to linac outputs." in rendered
    assert rendered.count("Linac ready for clinical use. Re-enable energies and document on MOSAIQ.") == 1
    assert "Manually enter here" not in rendered


def test_render_abc_weekly_org_text() -> None:
    entry = CandidateEntry(
        entry_type="abc_weekly",
        group_key="2026-04-07_ABC_abc_weekly",
        date="2026-04-07",
        title="ABC Weekly",
        site=None,
        unit="ABC",
        tags=["ABCWeekly"],
        performed_items=[
            PerformedItem(category="ABC x", label="ABC Weekly QC"),
            PerformedItem(category="ABC x", label="ABC Weekly QC"),
            PerformedItem(category="ABC x", label="ABC Weekly QC"),
        ],
        notable_prompts=["Split cable near PRS - Elekta still to repair."],
        source_ids=["qa:13611", "qa:13579", "qa:13580"],
    )

    rendered = render_candidate(entry)

    assert "**** [2026-04-07 Tue] ABC Weekly :ABCWeekly:" in rendered
    assert ":RM_GROUP_KEY: 2026-04-07_ABC_abc_weekly" in rendered
    assert "- ABC x :: ABC Weekly QC" in rendered
    assert "- ABC x :: ABC Weekly QC" in rendered
    assert "- ABC x :: ABC Weekly QC" in rendered
    assert "Manually enter here" not in rendered


def test_render_abc_ad_hoc_org_text() -> None:
    entry = CandidateEntry(
        entry_type="abc_ad_hoc",
        group_key="2026-04-14_ABC_abc_ad_hoc",
        date="2026-04-14",
        title="ABC Ad hoc QA",
        site=None,
        unit="ABC",
        tags=["ABCx"],
        performed_items=[
            PerformedItem(
                category="Problem Description",
                label="Balloon Tests 3B and 4B have been failing. These are not impacting on clinical performance, but may indicate balloon wear and tear.",
            ),
            PerformedItem(category="Work description", label="Elekta replaced the balloon valve."),
        ],
        notable_prompts=[
            "Performed Weekly as RTS, as well as RT daily runup. Unit continues to fail balloon tests 3B and 4B. Likely failing to seal balloon assembly against housing."
        ],
        source_ids=["service:324"],
        metadata={
            "url": "https://radmachine.example/demo-customer/servicelog/event/details/324/",
            "return_to_service_qa": ["ABC Weekly QC"],
        },
    )

    rendered = render_candidate(entry)

    assert "**** [2026-04-14 Tue] ABC Ad hoc QA :ABCx:" in rendered
    assert ":RM_GROUP_KEY: 2026-04-14_ABC_abc_ad_hoc" in rendered
    assert ":RM_SOURCE_IDS: service:324" in rendered
    assert ":URL: https://radmachine.example/demo-customer/servicelog/event/details/324/" in rendered
    assert "- Problem Description :: Balloon Tests 3B and 4B have been failing. These are not impacting on clinical performance, but may indicate balloon wear and tear." in rendered
    assert "- Work description :: Elekta replaced the balloon valve." in rendered
    assert "  Performed Weekly as RTS, as well as RT daily runup. Unit continues to fail balloon tests 3B and 4B. Likely failing to seal balloon assembly against housing." in rendered
    assert "- Return To Service QA ::" in rendered
    assert "  - ABC Weekly QC" in rendered


def test_render_service_ad_hoc_normalizes_multiline_problem_description() -> None:
    entry = CandidateEntry(
        entry_type="abc_ad_hoc",
        group_key="2026-04-14_ABC_abc_ad_hoc",
        date="2026-04-14",
        title="ABC Ad hoc QA",
        site=None,
        unit="ABC",
        tags=["ABCx"],
        performed_items=[
            PerformedItem(
                category="Problem Description",
                label="Balloon Tests 3B and 4B have been failing.\r\nThese are not impacting on clinical performance, but may indicate balloon wear and tear.",
            ),
        ],
        notable_prompts=[],
        source_ids=["service:324"],
        metadata={"url": "https://radmachine.example/demo-customer/servicelog/event/details/324/"},
    )

    rendered = render_candidate(entry)

    assert "\r" not in rendered
    assert "- Problem Description :: Balloon Tests 3B and 4B have been failing." in rendered
    assert "  These are not impacting on clinical performance, but may indicate balloon wear and tear." in rendered

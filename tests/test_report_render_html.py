from __future__ import annotations

from radlog.report_models import QaReport, QaIssue
from radlog.report_renderers.html import render_qa_html


def test_render_qa_html_groups_issues_and_links_sessions() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue(
                "action",
                "LAx",
                "Output",
                "CAX output",
                value=100.12345,
                session_url="https://example.test/session/1/",
            ),
            _issue("comment", "CTx", "CT Monthly", "HU constancy", comment="Please review.", commenter="reviewer"),
        ],
    )

    html = render_qa_html(report, title="Weekly QA Comments")

    assert "<!doctype html>" in html
    assert "Weekly QA Comments" in html
    assert "2026-07-18 to 2026-07-25" in html
    assert "LAx" in html
    assert "CTx" in html
    assert "<table>" in html
    assert "CAX output" in html
    assert "<th>Reference</th>" not in html
    assert "<th>Comment</th>" not in html
    assert ">100.123<" in html
    assert "Please review." in html
    assert "<strong>reviewer</strong>: Please review." in html
    assert 'href="https://example.test/session/1/"' in html
    assert 'class="value"' in html
    assert 'class="status-action"' in html
    assert "grouped by" not in html


def test_render_qa_html_does_not_show_reference_urls() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue(
                "normal",
                "ABC x",
                "ABC Weekly QC",
                "Balloon functionality",
                reference="https://example.test/api/qa/references/2/",
                raw={"reference": "https://example.test/api/qa/references/2/"},
            )
        ],
    )

    html = render_qa_html(report)

    assert "https://example.test/api/qa/references/2/" not in html
    assert "Balloon functionality" in html


def test_render_qa_html_collapses_session_comments() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue("comment", "LAx", "Output", "Session comment", comment="First note.", commenter="user-a"),
            _issue("comment", "LAx", "Output", "Session comment", comment="Second note.", commenter="user-b"),
        ],
    )

    html = render_qa_html(report)

    assert ">Session comment<" not in html
    assert "<strong>user-a</strong>: First note." in html
    assert "<strong>user-b</strong>: Second note." in html
    assert 'class="session-comments"' in html


def test_render_qa_html_can_group_by_date() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue("normal", "LAx", "Output", "CAX output"),
            _issue("normal", "CTx", "CT Monthly", "HU constancy"),
        ],
    )

    html = render_qa_html(report, group_by="date")

    assert "grouped by" not in html
    assert "2026-07-20 <span>2 row(s)</span>" in html


def test_render_qa_html_escapes_report_content() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue(
                "comment",
                "<script>alert(1)</script>",
                "QA <unsafe>",
                "Test & label",
                comment="<b>not html</b>",
            ),
        ],
    )

    html = render_qa_html(report)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>not html</b>" not in html
    assert "&lt;b&gt;not html&lt;/b&gt;" in html


def _issue(
    issue_type: str,
    equipment: str,
    collection: str,
    test: str,
    *,
    comment: str | None = None,
    session_url: str | None = None,
    reference: object | None = None,
    commenter: str | None = None,
    raw: dict | None = None,
    value: object = 4.2,
) -> QaIssue:
    return QaIssue(
        session_id="1",
        session_url=session_url,
        performed_at="2026-07-20T10:00:00+10:00",
        equipment_name=equipment,
        equipment_group=equipment,
        collection_name=collection,
        test_label=test,
        issue_type=issue_type,
        severity=issue_type,
        value=value,
        pass_fail=issue_type,
        comment=comment,
        reference=reference,
        commenter=commenter,
        raw=raw or {},
    )

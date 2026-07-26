from __future__ import annotations

from radlog.report_models import QaReport, QaIssue
from radlog.report_renderers.html import render_qa_html


def test_render_qa_html_groups_issues_and_links_sessions() -> None:
    report = QaReport(
        start="2026-07-18",
        end="2026-07-25",
        issues=[
            _issue("action", "LAx", "Output", "CAX output", session_url="https://example.test/session/1/"),
            _issue("comment", "CTx", "CT Monthly", "HU constancy", comment="Please review."),
        ],
    )

    html = render_qa_html(report)

    assert "<!doctype html>" in html
    assert "QA Report" in html
    assert "2026-07-18 to 2026-07-25" in html
    assert "LAx" in html
    assert "CTx" in html
    assert "CAX output" in html
    assert "Please review." in html
    assert 'href="https://example.test/session/1/"' in html


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
        value=4.2,
        pass_fail=issue_type,
        comment=comment,
        raw={},
    )

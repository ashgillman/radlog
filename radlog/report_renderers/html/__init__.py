"""HTML renderers for factual reports."""

from __future__ import annotations

from html import escape
from importlib.resources import files

from radlog.report_models import QaReport, QaIssue


def render_qa_html(report: QaReport) -> str:
    grouped: dict[str, list[QaIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue.equipment_group or "Unknown equipment", []).append(issue)

    sections = "\n".join(_render_equipment_section(equipment, grouped[equipment]) for equipment in sorted(grouped))
    if not sections:
        sections = '<section class="empty"><p>No matching QA issues.</p></section>'

    return (
        _template()
        .replace("{{ style }}", _style())
        .replace("{{ start }}", escape(report.start))
        .replace("{{ end }}", escape(report.end))
        .replace("{{ issue_count }}", str(len(report.issues)))
        .replace("{{ sections }}", sections)
    )


def _render_equipment_section(equipment: str, issues: list[QaIssue]) -> str:
    rendered_issues = "\n".join(_render_issue(issue) for issue in issues)
    return f"""<section>
  <h2>{escape(equipment)} <span class="subhead">{len(issues)} issue(s)</span></h2>
  {rendered_issues}
</section>"""


def _render_issue(issue: QaIssue) -> str:
    issue_class = _css_class(issue.issue_type)
    date = escape(issue.performed_at[:10] if issue.performed_at else "unknown-date")
    issue_type = escape(issue.issue_type)
    value = escape(repr(issue.value))
    collection = escape(issue.collection_name or "Unknown QA")
    test = escape(issue.test_label or "Unknown test")
    link = _render_link(issue)
    commenter = f'<span class="pill">commenter: {escape(issue.commenter)}</span>' if issue.commenter else ""
    comment = f'<div class="comment">{escape(issue.comment)}</div>' if issue.comment else ""
    return f"""<article class="{issue_class}">
  <div class="meta">
    <span class="pill">{date}</span>
    <span class="pill">{issue_type}</span>
    <span class="pill">value={value}</span>
    {commenter}
    {link}
  </div>
  <div class="test">{test}</div>
  <div class="collection">{collection}</div>
  {comment}
</article>"""


def _render_link(issue: QaIssue) -> str:
    if not issue.session_url:
        return ""
    url = escape(issue.session_url, quote=True)
    return f'<a class="pill" href="{url}">RadMachine</a>'


def _css_class(issue_type: str) -> str:
    if issue_type in {"action", "tolerance", "comment"}:
        return issue_type
    return "issue"


def _template() -> str:
    return files(__package__).joinpath("template.html").read_text(encoding="utf-8")


def _style() -> str:
    return files(__package__).joinpath("style.css").read_text(encoding="utf-8")

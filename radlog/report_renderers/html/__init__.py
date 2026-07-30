"""HTML renderers for factual reports."""

from __future__ import annotations

from html import escape
from importlib.resources import files
from typing import Any

from radlog.report_models import QaReport, QaIssue


def render_qa_html(report: QaReport, *, title: str = "QA Report", group_by: str = "equipment") -> str:
    grouped = _group_issues(report.issues, group_by=group_by)
    sections = "\n".join(
        _render_group_section(group_name, grouped[group_name])
        for group_name in sorted(grouped)
    )
    if not sections:
        sections = '<section class="empty"><p>No matching QA rows.</p></section>'

    return (
        _template()
        .replace("{{ style }}", _style())
        .replace("{{ title }}", escape(title))
        .replace("{{ start }}", escape(report.start))
        .replace("{{ end }}", escape(report.end))
        .replace("{{ issue_count }}", str(len(report.issues)))
        .replace("{{ sections }}", sections)
    )


def _group_issues(issues: list[QaIssue], *, group_by: str) -> dict[str, list[QaIssue]]:
    grouped: dict[str, list[QaIssue]] = {}
    for issue in issues:
        grouped.setdefault(_group_key(issue, group_by=group_by), []).append(issue)
    return grouped


def _group_key(issue: QaIssue, *, group_by: str) -> str:
    if group_by == "date":
        return issue.performed_at[:10] if issue.performed_at else "unknown-date"
    return issue.equipment_group or "Unknown equipment"


def _render_group_section(group_name: str, issues: list[QaIssue]) -> str:
    by_collection: dict[str, list[QaIssue]] = {}
    for issue in issues:
        key = issue.collection_name or "Unknown QA"
        by_collection.setdefault(key, []).append(issue)

    tables = "\n".join(
        _render_collection_table(collection_name, by_collection[collection_name])
        for collection_name in sorted(by_collection)
    )
    return f"""<section class="report-group">
  <h2>{escape(group_name)} <span>{len(issues)} row(s)</span></h2>
  {tables}
</section>"""


def _render_collection_table(collection_name: str, issues: list[QaIssue]) -> str:
    rows = "\n".join(_render_issue_rows(issue) for issue in issues if not _is_session_comment(issue))
    session_comments = _render_session_comments([issue for issue in issues if _is_session_comment(issue)])
    session_url = next((issue.session_url for issue in issues if issue.session_url), None)
    link = f' <a href="{escape(session_url, quote=True)}">RadMachine</a>' if session_url else ""
    dates = sorted({issue.performed_at[:10] for issue in issues if issue.performed_at})
    date_text = f'<span class="table-date">{escape(", ".join(dates))}</span>' if dates else ""
    return f"""<article class="test-list">
  <h3>{escape(collection_name)}{link}{date_text}</h3>
  <table>
    <colgroup>
      <col>
      <col class="value-column">
      <col class="url-column">
    </colgroup>
    <thead>
      <tr>
        <th>Test</th>
        <th>Value</th>
        <th>URL</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  {session_comments}
</article>"""


def _render_issue_rows(issue: QaIssue) -> str:
    issue_class = _css_class(issue.issue_type)
    result_row = f"""<tr class="{issue_class}">
  <td>{escape(issue.test_label or "Unknown test")}</td>
  <td class="value">{escape(_display_value(issue))}</td>
  <td>{_render_link(issue)}</td>
</tr>"""
    comment = _display_comment(issue)
    if not comment:
        return result_row
    commenter = escape(issue.commenter or "Comment")
    return f"""{result_row}
<tr class="{issue_class} comment-row">
  <td class="comment" colspan="3"><strong>{commenter}</strong>: {escape(comment)}</td>
</tr>"""


def _render_session_comments(issues: list[QaIssue]) -> str:
    if not issues:
        return ""
    comments = "\n".join(_render_comment_line(issue) for issue in issues if issue.comment)
    if not comments:
        return ""
    return f"""<div class="session-comments">
  {comments}
</div>"""


def _display_value(issue: QaIssue) -> str:
    raw_value = _first_raw_value(
        issue.raw,
        "valueDisplay",
        "value_display",
        "stringValue",
        "string_value",
        "diffDisplay",
        "diff_display",
    )
    if raw_value not in (None, ""):
        return str(raw_value)
    if issue.value is None:
        return ""
    return _format_value(issue.value)


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _display_comment(issue: QaIssue) -> str:
    if issue.comment:
        return issue.comment
    return ""


def _render_comment_line(issue: QaIssue) -> str:
    commenter = escape(issue.commenter or "Comment")
    return f"<strong>{commenter}</strong>: {escape(issue.comment or '')}"


def _is_session_comment(issue: QaIssue) -> bool:
    return issue.issue_type == "comment" and (issue.test_label or "") == "Session comment"


def _first_raw_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _render_link(issue: QaIssue) -> str:
    if not issue.session_url:
        return ""
    url = escape(issue.session_url, quote=True)
    return f'<a href="{url}">Open</a>'


def _css_class(issue_type: str) -> str:
    if issue_type == "action":
        return "status-action"
    if issue_type == "tolerance":
        return "status-tolerance"
    if issue_type == "skipped":
        return "status-skipped"
    if issue_type == "comment":
        return "status-comment"
    return "status-ok"


def _template() -> str:
    return files(__package__).joinpath("template.html").read_text(encoding="utf-8")


def _style() -> str:
    return files(__package__).joinpath("style.css").read_text(encoding="utf-8")

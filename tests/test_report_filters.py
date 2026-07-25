from __future__ import annotations

import pytest

from radlog.config import ConfigError
from radlog.report_filters import apply_issue_filters, parse_where
from radlog.report_models import QaIssue


def test_parse_where_supports_find_style_boolean_operators() -> None:
    issues = [
        _issue("action", "LAx", "Monthly output", "CAX output"),
        _issue("tolerance", "CTx", "CT Monthly", "HU constancy"),
        _issue("comment", "ABC x", "Weekly", "Setup note"),
    ]

    expression = parse_where(
        '( issue = action -o issue = tolerance ) -and -not equipment contains "ABC"'
    )

    assert [issue.test_label for issue in apply_issue_filters(issues, [expression])] == [
        "CAX output",
        "HU constancy",
    ]


def test_parse_where_supports_implicit_and_and_bang_not() -> None:
    issues = [
        _issue("action", "LAx", "Monthly output", "CAX output"),
        _issue("action", "ABC x", "Weekly", "Setup note"),
    ]

    expression = parse_where('issue = action ! equipment contains "ABC"')

    assert [issue.equipment_name for issue in apply_issue_filters(issues, [expression])] == ["LAx"]


def test_parse_where_supports_in_contains_matches_exists_and_missing() -> None:
    issues = [
        _issue("action", "LAx", "Monthly output", "CAX output", comment="Repeated."),
        _issue("tolerance", "CTx", "CT Monthly", "HU constancy"),
        _issue("comment", "ABC x", "Weekly", "Setup note", comment="Note only."),
    ]

    expression = parse_where(
        'issue in action,tolerance -and collection contains monthly -and test matches "output|HU" -and comment exists'
    )

    assert [issue.test_label for issue in apply_issue_filters(issues, [expression])] == ["CAX output"]

    expression = parse_where("comment missing")

    assert [issue.test_label for issue in apply_issue_filters(issues, [expression])] == ["HU constancy"]


def test_parse_where_treats_comma_as_low_precedence_or() -> None:
    issues = [
        _issue("action", "LAx", "Monthly output", "CAX output"),
        _issue("tolerance", "CTx", "CT Monthly", "HU constancy"),
        _issue("comment", "ABC x", "Weekly", "Setup note"),
    ]

    expression = parse_where("equipment = LAx , equipment = ABC x")

    assert [issue.equipment_name for issue in apply_issue_filters(issues, [expression])] == ["LAx", "ABC x"]


def test_repeated_where_expressions_are_combined_with_and() -> None:
    issues = [
        _issue("action", "LAx", "Monthly output", "CAX output"),
        _issue("tolerance", "LAx", "Monthly output", "Flatness"),
        _issue("action", "CTx", "CT Monthly", "HU constancy"),
    ]

    expressions = [parse_where("equipment = LAx"), parse_where("issue = action")]

    assert [issue.test_label for issue in apply_issue_filters(issues, expressions)] == ["CAX output"]


def test_parse_where_filters_by_resolved_commenter() -> None:
    issues = [
        _issue("comment", "LAx", "Monthly output", "CAX output", comment="Repeated.", commenter="example-user"),
        _issue("comment", "LAx", "Monthly output", "Flatness", comment="Repeated.", commenter="other-user"),
    ]

    expression = parse_where("commenter = example-user")

    assert [issue.test_label for issue in apply_issue_filters(issues, [expression])] == ["CAX output"]


def test_parse_where_reports_invalid_fields_and_expressions() -> None:
    with pytest.raises(ConfigError, match="Unknown report filter field"):
        parse_where("unknown = value")

    with pytest.raises(ConfigError, match="Expected report filter value"):
        parse_where("issue =")

    with pytest.raises(ConfigError, match="Expected"):
        parse_where("( issue = action")


def _issue(
    issue_type: str,
    equipment: str,
    collection: str,
    test: str,
    *,
    comment: str | None = None,
    commenter: str | None = None,
) -> QaIssue:
    return QaIssue(
        session_id="1",
        session_url=None,
        performed_at="2026-07-20T10:00:00+10:00",
        equipment_name=equipment,
        equipment_group=equipment,
        collection_name=collection,
        test_label=test,
        issue_type=issue_type,
        severity=issue_type,
        value=None,
        pass_fail=issue_type,
        comment=comment,
        commenter=commenter,
        raw={},
    )

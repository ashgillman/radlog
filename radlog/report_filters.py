"""Find-style boolean filters for report issues."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from typing import Protocol

from .config import ConfigError
from .report_models import QaIssue


class IssuePredicate(Protocol):
    def matches(self, issue: QaIssue) -> bool: ...


@dataclass(frozen=True, slots=True)
class Predicate:
    field: str
    operator: str
    value: str | None = None

    def matches(self, issue: QaIssue) -> bool:
        values = _field_values(issue, self.field)
        if self.operator == "exists":
            return any(value != "" for value in values)
        if self.operator == "missing":
            return not any(value != "" for value in values)

        expected = self.value or ""
        if self.operator == "=":
            return any(value.casefold() == expected.casefold() for value in values)
        if self.operator == "!=":
            return all(value.casefold() != expected.casefold() for value in values)
        if self.operator == "in":
            expected_values = {item.strip().casefold() for item in expected.split(",") if item.strip()}
            return any(value.casefold() in expected_values for value in values)
        if self.operator == "not-in":
            expected_values = {item.strip().casefold() for item in expected.split(",") if item.strip()}
            return all(value.casefold() not in expected_values for value in values)
        if self.operator == "contains":
            return any(expected.casefold() in value.casefold() for value in values)
        if self.operator == "matches":
            return any(re.search(expected, value) for value in values)
        raise ConfigError(f"Unknown report filter operator {self.operator!r}")


@dataclass(frozen=True, slots=True)
class Not:
    expression: IssuePredicate

    def matches(self, issue: QaIssue) -> bool:
        return not self.expression.matches(issue)


@dataclass(frozen=True, slots=True)
class And:
    left: IssuePredicate
    right: IssuePredicate

    def matches(self, issue: QaIssue) -> bool:
        return self.left.matches(issue) and self.right.matches(issue)


@dataclass(frozen=True, slots=True)
class Or:
    left: IssuePredicate
    right: IssuePredicate

    def matches(self, issue: QaIssue) -> bool:
        return self.left.matches(issue) or self.right.matches(issue)


VALID_FIELDS = {
    "collection",
    "comment",
    "commenter",
    "date",
    "equipment",
    "equipment_group",
    "issue",
    "session",
    "severity",
    "test",
    "user",
    "value",
}

VALUE_OPERATORS = {"=", "!=", "in", "not-in", "contains", "matches"}
UNARY_OPERATORS = {"exists", "missing"}
AND_OPERATORS = {"-a", "-and"}
OR_OPERATORS = {"-o", "-or"}


def parse_where(expression: str) -> IssuePredicate:
    parser = _Parser(_tokenize(expression))
    parsed = parser.parse_comma()
    if not parser.at_end:
        raise ConfigError(f"Unexpected report filter token {parser.peek()!r}")
    return parsed


def apply_issue_filters(issues: list[QaIssue], expressions: list[IssuePredicate]) -> list[QaIssue]:
    if not expressions:
        return issues
    return [issue for issue in issues if all(expression.matches(issue) for expression in expressions)]


def exact_user_filter_value(expression: IssuePredicate) -> str | None:
    """Return an exact user constraint that is safe to push down to RadMachine.

    This deliberately ignores OR/NOT/contains/matches cases. It is only safe to
    push down a predicate that the final client-side filter also requires.
    """
    if isinstance(expression, Predicate) and expression.field == "user" and expression.operator == "=":
        return expression.value
    if isinstance(expression, And):
        return exact_user_filter_value(expression.left) or exact_user_filter_value(expression.right)
    return None


def issue_filter_for_types(issue_types: set[str]) -> IssuePredicate:
    return Predicate("issue", "in", ",".join(sorted(issue_types)))


def _tokenize(expression: str) -> list[str]:
    lexer = shlex.shlex(expression, posix=True, punctuation_chars="()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0

    @property
    def at_end(self) -> bool:
        return self.position >= len(self.tokens)

    def peek(self) -> str | None:
        if self.at_end:
            return None
        return self.tokens[self.position]

    def advance(self) -> str:
        if self.at_end:
            raise ConfigError("Unexpected end of report filter expression")
        token = self.tokens[self.position]
        self.position += 1
        return token

    def parse_comma(self) -> IssuePredicate:
        expression = self.parse_or()
        while self.peek() == ",":
            self.advance()
            expression = Or(expression, self.parse_or())
        return expression

    def parse_or(self) -> IssuePredicate:
        expression = self.parse_and()
        while self.peek() in OR_OPERATORS:
            self.advance()
            expression = Or(expression, self.parse_and())
        return expression

    def parse_and(self) -> IssuePredicate:
        expression = self.parse_not()
        while self._starts_implicit_and() or self.peek() in AND_OPERATORS:
            if self.peek() in AND_OPERATORS:
                self.advance()
            expression = And(expression, self.parse_not())
        return expression

    def parse_not(self) -> IssuePredicate:
        if self.peek() in {"!", "-not"}:
            self.advance()
            return Not(self.parse_not())
        return self.parse_primary()

    def parse_primary(self) -> IssuePredicate:
        token = self.peek()
        if token == "(":
            self.advance()
            expression = self.parse_comma()
            if self.peek() != ")":
                raise ConfigError("Expected ')' in report filter expression")
            self.advance()
            return expression
        return self.parse_predicate()

    def parse_predicate(self) -> IssuePredicate:
        field = self.advance()
        if field not in VALID_FIELDS:
            raise ConfigError(f"Unknown report filter field {field!r}")

        operator = self.advance()
        if operator in UNARY_OPERATORS:
            return Predicate(field, operator)
        if operator not in VALUE_OPERATORS:
            raise ConfigError(f"Unknown report filter operator {operator!r}")

        value_parts: list[str] = []
        while not self.at_end and not self._is_expression_boundary(self.peek()):
            value_parts.append(self.advance())
        if not value_parts:
            raise ConfigError(f"Expected report filter value after {field} {operator}")
        return Predicate(field, operator, " ".join(value_parts))

    def _starts_implicit_and(self) -> bool:
        token = self.peek()
        return token in {"!", "-not", "("} or token in VALID_FIELDS

    @staticmethod
    def _is_expression_boundary(token: str | None) -> bool:
        return token is None or token == ")" or token == "," or token in AND_OPERATORS or token in OR_OPERATORS or token in {"!", "-not"}


def _field_values(issue: QaIssue, field: str) -> list[str]:
    values: list[object | None]
    if field == "issue":
        values = [issue.issue_type]
    elif field == "severity":
        values = [issue.severity]
    elif field == "equipment":
        values = [issue.equipment_name]
    elif field == "equipment_group":
        values = [issue.equipment_group]
    elif field == "collection":
        values = [issue.collection_name]
    elif field == "test":
        values = [issue.test_label]
    elif field == "comment":
        values = [issue.comment]
    elif field == "value":
        values = [issue.value]
    elif field == "date":
        values = [issue.performed_at[:10] if issue.performed_at else None]
    elif field == "session":
        values = [issue.session_id, issue.session_url]
    elif field == "user":
        values = [issue.user] + _raw_values(issue.raw, ("created_by", "modified_by", "user", "username"))
    elif field == "commenter":
        values = [issue.commenter]
    else:
        raise ConfigError(f"Unknown report filter field {field!r}")
    return [str(value) for value in values if value is not None and str(value) != ""]


def _raw_values(payload: dict, keys: tuple[str, ...]) -> list[object | None]:
    values: list[object | None] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            values.extend(value.get(nested_key) for nested_key in ("username", "name", "id"))
        else:
            values.append(value)
    return values

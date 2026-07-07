"""Thin dataclass mirrors for RadMachine API objects.

These classes intentionally model only fields radlog currently uses. Each
object preserves the complete API payload in `raw` so unknown or newly added
fields are still available to workflow code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiObject:
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def remote_id(self) -> str:
        return extract_id(self.url)


@dataclass(slots=True)
class TestListInstance(ApiObject):
    site_url: str | None = None
    report_url: str | None = None
    created: str | None = None
    modified: str | None = None
    work_started: str | None = None
    work_completed: str | None = None
    due_date: str | None = None
    flagged: bool = False
    reviewed: str | bool | None = None
    unit_test_collection: str | None = None
    test_list: str | None = None
    created_by: str | None = None
    modified_by: str | None = None
    comments: list[dict[str, Any]] = field(default_factory=list)
    test_instances: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "TestListInstance":
        return cls(
            url=str(payload.get("url") or ""),
            site_url=_optional_str(payload.get("site_url")),
            report_url=_optional_str(payload.get("report_url")),
            created=_optional_str(payload.get("created")),
            modified=_optional_str(payload.get("modified")),
            work_started=_optional_str(payload.get("work_started")),
            work_completed=_optional_str(payload.get("work_completed")),
            due_date=_optional_str(payload.get("due_date")),
            flagged=bool(payload.get("flagged")),
            reviewed=payload.get("reviewed"),
            unit_test_collection=_optional_str(payload.get("unit_test_collection")),
            test_list=_optional_str(payload.get("test_list")),
            created_by=_optional_str(payload.get("created_by")),
            modified_by=_optional_str(payload.get("modified_by")),
            comments=_list_of_dicts(payload.get("comments")),
            test_instances=_list_of_dicts(payload.get("test_instances")),
            raw=payload,
        )

    @property
    def performed_at(self) -> str | None:
        return self.work_completed or self.work_started

    @property
    def status(self) -> str:
        if self.flagged:
            return "flagged"
        if self.reviewed:
            return "reviewed"
        return "completed"


@dataclass(slots=True)
class TestInstance(ApiObject):
    value: Any = None
    pass_fail: str | bool | None = None
    skipped: bool | None = None
    work_completed: str | None = None
    unit_test_info: str | None = None
    test_list_instance: str | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "TestInstance":
        return cls(
            url=str(payload.get("url") or ""),
            value=payload.get("value"),
            pass_fail=payload.get("pass_fail"),
            skipped=payload.get("skipped"),
            work_completed=_optional_str(payload.get("work_completed")),
            unit_test_info=_optional_str(payload.get("unit_test_info")),
            test_list_instance=_optional_str(payload.get("test_list_instance")),
            raw=payload,
        )


@dataclass(slots=True)
class UnitTestCollection(ApiObject):
    name: str | None = None
    unit: str | None = None
    frequency: str | None = None
    due_date: str | None = None
    last_instance: str | None = None
    test_list: str | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "UnitTestCollection":
        return cls(
            url=str(payload.get("url") or ""),
            name=_optional_str(payload.get("name")),
            unit=_optional_str(payload.get("unit")),
            frequency=_optional_str(payload.get("frequency")),
            due_date=_optional_str(payload.get("due_date")),
            last_instance=_optional_str(payload.get("last_instance")),
            test_list=_optional_str(payload.get("test_list")),
            raw=payload,
        )


@dataclass(slots=True)
class Unit(ApiObject):
    name: str | None = None
    site: str | None = None
    type: str | None = None
    active: bool | None = None
    is_serviceable: bool | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Unit":
        return cls(
            url=str(payload.get("url") or ""),
            name=_optional_str(payload.get("name")),
            site=_optional_str(payload.get("site")),
            type=_optional_str(payload.get("type")),
            active=payload.get("active"),
            is_serviceable=payload.get("is_serviceable"),
            raw=payload,
        )

    @property
    def short_name_and_site(self) -> tuple[str | None, str | None]:
        return split_unit_name(self.name)


@dataclass(slots=True)
class ServiceEvent(ApiObject):
    datetime_created: str | None = None
    datetime_modified: str | None = None
    datetime_service: str | None = None
    problem_description: str | None = None
    work_description: str | None = None
    unit_service_area: str | None = None
    service_type: str | None = None
    service_status: str | None = None
    user_created_by: str | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ServiceEvent":
        return cls(
            url=str(payload.get("url") or ""),
            datetime_created=_optional_str(payload.get("datetime_created")),
            datetime_modified=_optional_str(payload.get("datetime_modified")),
            datetime_service=_optional_str(payload.get("datetime_service")),
            problem_description=_optional_str(payload.get("problem_description")),
            work_description=_optional_str(payload.get("work_description")),
            unit_service_area=_optional_str(payload.get("unit_service_area")),
            service_type=_optional_str(payload.get("service_type")),
            service_status=_optional_str(payload.get("service_status")),
            user_created_by=_optional_str(payload.get("user_created_by")),
            raw=payload,
        )

    @property
    def performed_at(self) -> str | None:
        return self.datetime_service or self.datetime_created


@dataclass(slots=True)
class ServiceLogReturnToServiceQA(ApiObject):
    datetime_assigned: str | None = None
    unit_test_collection: str | None = None
    test_list_instance: str | None = None
    user_assigned_by: str | None = None
    service_event: str | None = None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ServiceLogReturnToServiceQA":
        return cls(
            url=str(payload.get("url") or ""),
            datetime_assigned=_optional_str(payload.get("datetime_assigned")),
            unit_test_collection=_optional_str(payload.get("unit_test_collection")),
            test_list_instance=_optional_str(payload.get("test_list_instance")),
            user_assigned_by=_optional_str(payload.get("user_assigned_by")),
            service_event=_optional_str(payload.get("service_event")),
            raw=payload,
        )


def extract_id(url: str | None) -> str:
    if not url:
        return ""
    return url.rstrip("/").rsplit("/", 1)[-1]


def split_unit_name(name: str | None) -> tuple[str | None, str | None]:
    if not name:
        return None, None
    if " - " not in name:
        return name, None
    unit, site = name.split(" - ", 1)
    return unit, site


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

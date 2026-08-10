"""TCC QuickCheck constancy composite example.

This is site workflow code, not radlog library core. It gathers source QA
sessions, extracts QuickCheck and monthly solid-water output values, and builds
a dry-run payload for the target Quickcheck Constancy test.

It only submits data to RadMachine when explicitly called with --practice-run
or --upload.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date as Date
from datetime import timedelta
import json
from typing import Any

from radlog.api import RadMachineClient
from radlog.collect import ResolvedQaSession as ResolvedSession
from radlog.collect import collect_resolved_qa_sessions_for_collections
from radlog.collect import collect_unit_test_collections, resolve_qa_session
from radlog.config import load_config, resolve_config_path
from radlog.qa_results import attach_test_result_slugs, numeric_test_value_by_slug
from radlog.rm_models import TestListInstance


PRACTICE_TARGET_UTC_ID = 587
TARGET_TEST_LIST_NAME = "Quickcheck Constancy"
TARGET_UNIT_NAME_TEMPLATE = "PTW Quickcheck: {serial}"
RELATIVE_DATE_WINDOWS = {
    "day": 1,
    "week": 7,
    "month": 30,
}

# These maps are deliberately kept in this example module because they are TCC
# workflow knowledge, not stable RadMachine API semantics.
PHOTON_QUICKCHECK_OUTPUT_SLUGS = {
    "6 MV": "quickcheck_cax_output_6_mv",
    "6 FFF": "quickcheck_cax_output_6_mv_fff",
    "10 MV": "quickcheck_cax_output_10_mv",
}
ELECTRON_QUICKCHECK_OUTPUT_SLUGS = {
    "6 MeV": "quickcheck_cax_output_6_mev",
    "8 MeV": "quickcheck_cax_output_8_mev",
    "10 MeV": "quickcheck_cax_output_10_mev",
    "12 MeV": "quickcheck_cax_output_12_mev",
    "15 MeV": "quickcheck_cax_output_15_mev",
}
QUICKCHECK_SERIAL_ORDER = 0

MONTHLY_OUTPUT_DEVIATION_SLUGS = {
    "6 MV": "linac_monthly_output_deviation_6_mv",
    "6 FFF": "linac_monthly_output_deviation_6_fff",
    "10 MV": "linac_monthly_output_deviation_10_mv",
    "6 MeV": "linac_monthly_output_deviation_6_mev",
    "8 MeV": "linac_monthly_output_deviation_8_mev",
    "10 MeV": "linac_monthly_output_deviation_10_mev",
    "12 MeV": "linac_monthly_output_deviation_12_mev",
    "15 MeV": "linac_monthly_output_deviation_15_mev",
}

TARGET_QC_OUTPUT_SLUGS = {
    "6 MV": "quickcheck_constancy_output_6mv",
    "6 FFF": "quickcheck_constancy_output_6fff",
    "10 MV": "quickcheck_constancy_output_10mv",
    "6 MeV": "quickcheck_constancy_output_6mev",
    "8 MeV": "quickcheck_constancy_output_8mev",
    "10 MeV": "quickcheck_constancy_output_10mev",
    "12 MeV": "quickcheck_constancy_output_12mev",
    "15 MeV": "quickcheck_constancy_output_15mev",
}
TARGET_SOLID_WATER_SLUGS = {
    "6 MV": "quickcheck_constancy_solid_water_output_6mv",
    "6 FFF": "quickcheck_constancy_solid_water_output_6fff",
    "10 MV": "quickcheck_constancy_solid_water_output_10mv",
    "6 MeV": "quickcheck_constancy_solid_water_output_6mev",
    "8 MeV": "quickcheck_constancy_solid_water_output_8mev",
    "10 MeV": "quickcheck_constancy_solid_water_output_10mev",
    "12 MeV": "quickcheck_constancy_solid_water_output_12mev",
    "15 MeV": "quickcheck_constancy_solid_water_output_15mev",
}
REQUIRED_TARGET_ENERGIES = {"6 MV", "10 MV"}


@dataclass(slots=True)
class SourceSelection:
    role: str
    label: str
    options: list[ResolvedSession] = field(default_factory=list)

    @property
    def default(self) -> ResolvedSession | None:
        return self.options[0] if self.options else None


@dataclass(slots=True)
class EnergyDraft:
    energy: str
    quickcheck_output: float | None = None
    solid_water_output_deviation: float | None = None
    quickcheck_session_id: str | None = None
    quickcheck_url: str | None = None
    quickcheck_work_started: str | None = None
    quickcheck_work_completed: str | None = None
    monthly_session_id: str | None = None
    monthly_url: str | None = None
    monthly_work_started: str | None = None
    monthly_work_completed: str | None = None


@dataclass(slots=True)
class QuickcheckConstancyDraft:
    linac: str | None
    quickcheck_serial: str | None
    target_utc_id: int | None = None
    source_session_ids: list[str] = field(default_factory=list)
    work_started: str | None = None
    work_completed: str | None = None
    energies: dict[str, EnergyDraft] = field(default_factory=dict)
    target_values: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["energies"] = {energy: asdict(draft) for energy, draft in self.energies.items()}
        return payload


def build_submission_payload(
    draft: QuickcheckConstancyDraft,
    *,
    target_utc_id: int = PRACTICE_TARGET_UTC_ID,
    battery_check: bool | None = None,
) -> dict[str, Any]:
    _validate_submission_draft(draft)
    return {
        "unit_test_collection": target_utc_id,
        "work_started": draft.work_started,
        "work_completed": draft.work_completed,
        "tests": _submission_tests(draft, battery_check=battery_check),
        "comment": _submission_comment(draft),
    }


def submit_practice_qa(client: RadMachineClient, draft: QuickcheckConstancyDraft, *, battery_check: bool) -> dict:
    payload = build_submission_payload(draft, target_utc_id=PRACTICE_TARGET_UTC_ID, battery_check=battery_check)
    return client.perform_qa_session(**payload)


def submit_real_qa(client: RadMachineClient, draft: QuickcheckConstancyDraft, *, battery_check: bool) -> dict:
    target_utc_id = resolve_quickcheck_target_utc_id(client, draft)
    payload = build_submission_payload(draft, target_utc_id=target_utc_id, battery_check=battery_check)
    return client.perform_qa_session(**payload)


def resolve_quickcheck_target_utc_id(client: RadMachineClient, draft: QuickcheckConstancyDraft) -> int:
    """Resolve the target QuickCheck assignment from the source serial number.

    RadMachine's UnitTestCollection is the assignment of a test list to a unit.
    Resolving it by unit/test-list name avoids hardcoding live assignment IDs.
    """
    if not draft.quickcheck_serial:
        raise ValueError("QuickCheck serial is required to resolve the target assignment")
    unit_name = TARGET_UNIT_NAME_TEMPLATE.format(serial=draft.quickcheck_serial)
    collections = collect_unit_test_collections(
        client,
        unit=unit_name,
        collection_name_matches=lambda name: name == TARGET_TEST_LIST_NAME,
    )
    if len(collections) != 1:
        raise ValueError(
            f"Expected one {TARGET_TEST_LIST_NAME!r} assignment for {unit_name!r}; found {len(collections)}"
        )
    return int(collections[0].remote_id)


def _validate_submission_draft(draft: QuickcheckConstancyDraft) -> None:
    errors: list[str] = []
    if not draft.work_started:
        errors.append("work_started is required")
    if not draft.work_completed:
        errors.append("work_completed is required")
    if not draft.quickcheck_serial:
        errors.append("QuickCheck serial is required")
    for warning in draft.warnings:
        if warning.startswith("Multiple QuickCheck serials found"):
            errors.append(warning)
    for energy in sorted(REQUIRED_TARGET_ENERGIES):
        energy_draft = draft.energies.get(energy)
        if energy_draft is None or energy_draft.quickcheck_output is None:
            errors.append(f"Missing required QuickCheck output for {energy}")
        if energy_draft is None or energy_draft.solid_water_output_deviation is None:
            errors.append(f"Missing required monthly solid-water output deviation for {energy}")
    test_values = {
        key: value
        for key, value in draft.target_values.items()
        if key not in {"work_started", "work_completed"} and value is not None
    }
    if not test_values:
        errors.append("at least one target test value is required")
    if errors:
        raise ValueError("; ".join(errors))


def _submission_tests(draft: QuickcheckConstancyDraft, *, battery_check: bool | None = None) -> dict[str, dict[str, Any]]:
    tests = _skipped_target_input_tests()
    if battery_check is not None:
        tests["quickcheck_battery_check"] = {"value": battery_check}
    for slug, value in sorted(draft.target_values.items()):
        if slug not in {"work_started", "work_completed"} and value is not None:
            tests[slug] = {"value": value}
    for energy, energy_draft in sorted(draft.energies.items()):
        output_slug = TARGET_QC_OUTPUT_SLUGS.get(energy)
        if output_slug and energy_draft.quickcheck_output is None:
            tests[output_slug] = {"skipped": True}
        solid_water_slug = TARGET_SOLID_WATER_SLUGS.get(energy)
        if solid_water_slug and energy_draft.solid_water_output_deviation is None:
            tests[solid_water_slug] = {"skipped": True}
    return tests


def _skipped_target_input_tests() -> dict[str, dict[str, bool]]:
    return {
        slug: {"skipped": True}
        for slug in sorted(
            {"linac_selection", "quickcheck_battery_check", *TARGET_QC_OUTPUT_SLUGS.values(), *TARGET_SOLID_WATER_SLUGS.values()}
        )
    }


def _submission_comment(draft: QuickcheckConstancyDraft) -> str:
    lines = [
        "Compiled by radlog from source QA.",
        f"QuickCheck serial: {draft.quickcheck_serial or '<unknown>'}",
        "",
        "Source sessions:",
    ]
    seen: set[str] = set()
    for energy, source in sorted(draft.energies.items()):
        for label, session_id, url in (
            ("QuickCheck", source.quickcheck_session_id, source.quickcheck_url),
            ("Monthly dosimetry", source.monthly_session_id, source.monthly_url),
        ):
            if not session_id or not url:
                continue
            key = f"{label}:{session_id}"
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {energy} {label}: {url}")
    return "\n".join(lines)


def load_sessions_by_ids(client: RadMachineClient, session_ids: list[int]) -> list[ResolvedSession]:
    sessions = [resolve_qa_session(client, session_id) for session_id in session_ids]
    attach_test_definition_slugs(client, sessions)
    return sessions


def discover_source_sessions(
    client: RadMachineClient,
    linac: str,
    start_date: str,
    end_date: str | None = None,
    selected_date: str | None = None,
    ui: str = "args",
) -> list[SourceSelection]:
    """Find source sessions by anchoring on monthly dosimetry.

    Monthly dosimetry is much less frequent than QuickCheck, so it is used to
    choose the actual source date before same-day QuickCheck sessions are read.
    """
    end_date = end_date or start_date
    monthly_sessions = discover_monthly_source_sessions(client, linac, start_date, end_date)
    selected_date = selected_date or select_monthly_source_date(_session_dates(monthly_sessions), ui=ui)
    monthly_for_date = _sessions_on_date(monthly_sessions, selected_date)
    if not monthly_for_date:
        raise SystemExit(f"No monthly dosimetry source sessions found for {linac} on {selected_date}")
    quickcheck_for_date = discover_quickcheck_source_sessions(client, linac, selected_date)
    return _source_selections(monthly_for_date + quickcheck_for_date)


def discover_monthly_source_sessions(
    client: RadMachineClient,
    linac: str,
    start_date: str,
    end_date: str,
) -> list[ResolvedSession]:
    collections = collect_unit_test_collections(
        client,
        unit=linac,
        collection_name_matches=_is_monthly_source_collection,
    )
    sessions = collect_resolved_qa_sessions_for_collections(
        client,
        collections,
        start=start_date,
        end=end_date,
        extra_params={"limit": "20"},
    )
    attach_test_definition_slugs(client, sessions)
    return sessions


def discover_quickcheck_source_sessions(client: RadMachineClient, linac: str, performed_date: str) -> list[ResolvedSession]:
    collections = collect_unit_test_collections(
        client,
        unit=linac,
        collection_name_matches=_is_quickcheck_source_collection,
    )
    sessions = collect_resolved_qa_sessions_for_collections(
        client,
        collections,
        start=performed_date,
        end=performed_date,
        extra_params={"limit": "20"},
    )
    attach_test_definition_slugs(client, sessions)
    return sessions


def attach_test_definition_slugs(client: RadMachineClient, sessions: list[ResolvedSession]) -> None:
    attach_test_result_slugs(client, [resolved.session for resolved in sessions])


def find_sessions_for_linac_date(client: RadMachineClient, linac: str, performed_date: str) -> list[ResolvedSession]:
    """Find likely source sessions for a linac/date, defaulting duplicates to latest."""
    return select_latest_source_sessions(discover_source_sessions(client, linac, performed_date, selected_date=performed_date))


def select_latest_source_sessions(selections: list[SourceSelection]) -> list[ResolvedSession]:
    return [selection.default for selection in selections if selection.default is not None]


def compile_quickcheck_constancy(sessions: list[ResolvedSession]) -> QuickcheckConstancyDraft:
    linacs = sorted({session.short_unit_name for session in sessions if session.short_unit_name})
    draft = QuickcheckConstancyDraft(
        linac=linacs[0] if len(linacs) == 1 else None,
        quickcheck_serial=None,
        source_session_ids=[session.session_id for session in sessions],
        work_started=_earliest_work_started(sessions),
        work_completed=_latest_work_completed(sessions),
    )
    if len(linacs) > 1:
        draft.warnings.append(f"Multiple linacs found in source sessions: {', '.join(linacs)}")

    for session in sessions:
        collection = session.collection_name
        if collection == "Quickcheck Photons":
            _add_quickcheck_outputs(draft, session, PHOTON_QUICKCHECK_OUTPUT_SLUGS)
            _add_quickcheck_serial(draft, session)
        elif collection == "Quickcheck Electrons":
            _add_quickcheck_outputs(draft, session, ELECTRON_QUICKCHECK_OUTPUT_SLUGS)
            _add_quickcheck_serial(draft, session)
        elif collection.startswith("Linac Monthly :: Dosimetry :: Output and relative dosimetry :: "):
            energy = collection.rsplit(" :: ", 1)[-1]
            _add_solid_water_output(draft, session, energy)
        elif collection.startswith("Linac Monthly :: Dosimetry :: Output and energy constancy :: "):
            energy = collection.rsplit(" :: ", 1)[-1]
            _add_solid_water_output(draft, session, energy)
        else:
            draft.warnings.append(f"Ignored unsupported source collection {collection!r} from session {session.session_id}")

    if draft.linac:
        draft.target_values["linac_selection"] = draft.linac
    if draft.work_started:
        draft.target_values["work_started"] = draft.work_started
    if draft.work_completed:
        draft.target_values["work_completed"] = draft.work_completed
    for energy, energy_draft in draft.energies.items():
        output_slug = TARGET_QC_OUTPUT_SLUGS.get(energy)
        if output_slug and energy_draft.quickcheck_output is not None:
            draft.target_values[output_slug] = energy_draft.quickcheck_output
        solid_water_slug = TARGET_SOLID_WATER_SLUGS.get(energy)
        if solid_water_slug and energy_draft.solid_water_output_deviation is not None:
            draft.target_values[solid_water_slug] = energy_draft.solid_water_output_deviation

    _add_missing_value_warnings(draft)
    return draft


def _add_quickcheck_outputs(draft: QuickcheckConstancyDraft, session: ResolvedSession, slug_map: dict[str, str]) -> None:
    for energy, slug in slug_map.items():
        value = numeric_test_value_by_slug(session.session, slug)
        if value is None:
            continue
        energy_draft = draft.energies.setdefault(energy, EnergyDraft(energy=energy))
        energy_draft.quickcheck_output = value
        energy_draft.quickcheck_session_id = session.session_id
        energy_draft.quickcheck_url = session.session.site_url
        energy_draft.quickcheck_work_started = session.session.work_started
        energy_draft.quickcheck_work_completed = session.session.work_completed


def _add_quickcheck_serial(draft: QuickcheckConstancyDraft, session: ResolvedSession) -> None:
    serial = _string_value_at_order(session.session, QUICKCHECK_SERIAL_ORDER)
    if not serial:
        return
    if draft.quickcheck_serial and draft.quickcheck_serial != serial:
        draft.warnings.append(f"Multiple QuickCheck serials found: {draft.quickcheck_serial} and {serial}")
    draft.quickcheck_serial = serial


def _add_solid_water_output(draft: QuickcheckConstancyDraft, session: ResolvedSession, energy: str) -> None:
    slug = MONTHLY_OUTPUT_DEVIATION_SLUGS.get(energy)
    if slug is None:
        draft.warnings.append(f"No monthly output-deviation slug configured for {energy}")
        return
    value = numeric_test_value_by_slug(session.session, slug)
    if value is None:
        draft.warnings.append(f"Missing source result {slug} in monthly session {session.session_id}")
        return
    energy_draft = draft.energies.setdefault(energy, EnergyDraft(energy=energy))
    energy_draft.solid_water_output_deviation = value
    energy_draft.monthly_session_id = session.session_id
    energy_draft.monthly_url = session.session.site_url
    energy_draft.monthly_work_started = session.session.work_started
    energy_draft.monthly_work_completed = session.session.work_completed


def _earliest_work_started(sessions: list[ResolvedSession]) -> str | None:
    values = [session.session.work_started for session in sessions if session.session.work_started]
    return min(values) if values else None


def _latest_work_completed(sessions: list[ResolvedSession]) -> str | None:
    values = [session.session.work_completed for session in sessions if session.session.work_completed]
    return max(values) if values else None


def _string_value_at_order(session: TestListInstance, order: int) -> str | None:
    test = _test_instance_at_order(session, order)
    if test is None or test.get("skipped"):
        return None
    value = str(test.get("string_value") or "").strip()
    return value or None


def _test_instance_at_order(session: TestListInstance, order: int) -> dict[str, Any] | None:
    for test in session.test_instances:
        if test.get("order") == order:
            return test
    return None


def _add_missing_value_warnings(draft: QuickcheckConstancyDraft) -> None:
    for energy, energy_draft in sorted(draft.energies.items()):
        if energy_draft.quickcheck_output is None:
            draft.warnings.append(f"Missing QuickCheck output for {energy}")
        if energy_draft.solid_water_output_deviation is None:
            draft.warnings.append(f"Missing monthly solid-water output deviation for {energy}")


def _is_quickcheck_source_collection(name: str) -> bool:
    return name in {"Quickcheck Photons", "Quickcheck Electrons"}


def _is_monthly_source_collection(name: str) -> bool:
    return name.startswith(
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: "
    ) or name.startswith("Linac Monthly :: Dosimetry :: Output and energy constancy :: ")


def _session_dates(sessions: list[ResolvedSession]) -> list[str]:
    dates = {date for session in sessions if (date := _session_date(session))}
    return sorted(dates, reverse=True)


def _session_date(session: ResolvedSession) -> str | None:
    return session.session.performed_at[:10] if session.session.performed_at else None


def _sessions_on_date(sessions: list[ResolvedSession], selected_date: str) -> list[ResolvedSession]:
    return [session for session in sessions if _session_date(session) == selected_date]


def select_monthly_source_date(dates: list[str], ui: str = "args") -> str:
    if not dates:
        raise SystemExit("No monthly dosimetry source sessions found in the requested date range")
    if len(dates) == 1:
        return dates[0]
    if ui == "gui":
        return select_monthly_source_date_gui(dates)
    return select_monthly_source_date_tui(dates)


def select_monthly_source_date_tui(dates: list[str]) -> str:
    print("\nMonthly dosimetry dates:")
    for index, performed_date in enumerate(dates, start=1):
        print(f"  {index}. {performed_date}")
    raw_choice = input("Select monthly source date [1]: ").strip()
    choice = int(raw_choice or "1")
    if choice < 1 or choice > len(dates):
        raise SystemExit(f"Invalid monthly source date selection {choice}")
    return dates[choice - 1]


def select_monthly_source_date_gui(dates: list[str]) -> str:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"tkinter is not available: {exc}")

    root = tk.Tk()
    root.withdraw()
    try:
        prompt = "\n".join(f"{index}. {performed_date}" for index, performed_date in enumerate(dates, start=1))
        choice = simpledialog.askinteger(
            "Select Monthly Dosimetry Date",
            f"Monthly dosimetry dates\n\n{prompt}\n\nSelection",
            initialvalue=1,
            minvalue=1,
            maxvalue=len(dates),
        )
        if choice is None:
            raise SystemExit("Monthly source date selection cancelled")
        return dates[choice - 1]
    finally:
        root.destroy()


def _source_selections(sessions: list[ResolvedSession]) -> list[SourceSelection]:
    grouped: dict[str, list[ResolvedSession]] = {}
    labels: dict[str, str] = {}
    for session in sessions:
        role = _source_role(session.collection_name)
        if role is None:
            continue
        grouped.setdefault(role, []).append(session)
        labels[role] = _source_label(session.collection_name)

    selections: list[SourceSelection] = []
    for role in sorted(grouped, key=_source_role_sort_key):
        options = sorted(grouped[role], key=lambda session: session.session.performed_at or "", reverse=True)
        selections.append(SourceSelection(role=role, label=labels[role], options=options))
    return selections


def _source_role(collection_name: str) -> str | None:
    if collection_name == "Quickcheck Photons":
        return "quickcheck_photons"
    if collection_name == "Quickcheck Electrons":
        return "quickcheck_electrons"
    if collection_name.startswith("Linac Monthly :: Dosimetry :: Output and relative dosimetry :: "):
        energy = collection_name.rsplit(" :: ", 1)[-1]
        return f"monthly_photon_{energy}"
    if collection_name.startswith("Linac Monthly :: Dosimetry :: Output and energy constancy :: "):
        energy = collection_name.rsplit(" :: ", 1)[-1]
        return f"monthly_electron_{energy}"
    return None


def _source_label(collection_name: str) -> str:
    if collection_name == "Quickcheck Photons":
        return "Daily QuickCheck photons"
    if collection_name == "Quickcheck Electrons":
        return "Daily QuickCheck electrons"
    if collection_name.startswith("Linac Monthly :: Dosimetry :: "):
        return collection_name.replace("Linac Monthly :: Dosimetry :: ", "Monthly dosimetry :: ")
    return collection_name


def _source_role_sort_key(role: str) -> tuple[int, str]:
    if role == "quickcheck_photons":
        return (0, role)
    if role == "quickcheck_electrons":
        return (1, role)
    if role.startswith("monthly_photon_"):
        return (2, role)
    if role.startswith("monthly_electron_"):
        return (3, role)
    return (9, role)


def select_source_sessions_tui(selections: list[SourceSelection]) -> list[ResolvedSession]:
    selected: list[ResolvedSession] = []
    for selection in selections:
        if not selection.options:
            continue
        if len(selection.options) == 1:
            selected.append(selection.options[0])
            continue

        print(f"\n{selection.label}:")
        for index, option in enumerate(selection.options, start=1):
            print(f"  {index}. session {option.session_id} at {option.session.performed_at or 'unknown time'}")
        raw_choice = input("Select source session [1]: ").strip()
        choice = int(raw_choice or "1")
        if choice < 1 or choice > len(selection.options):
            raise SystemExit(f"Invalid selection {choice} for {selection.label}")
        selected.append(selection.options[choice - 1])
    return selected


def select_source_sessions_gui(selections: list[SourceSelection]) -> list[ResolvedSession]:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"tkinter is not available: {exc}")

    root = tk.Tk()
    root.withdraw()
    selected: list[ResolvedSession] = []
    try:
        for selection in selections:
            if not selection.options:
                continue
            if len(selection.options) == 1:
                selected.append(selection.options[0])
                continue
            prompt = "\n".join(
                f"{index}. session {option.session_id} at {option.session.performed_at or 'unknown time'}"
                for index, option in enumerate(selection.options, start=1)
            )
            choice = simpledialog.askinteger(
                "Select QuickCheck source",
                f"{selection.label}\n\n{prompt}\n\nSelection",
                initialvalue=1,
                minvalue=1,
                maxvalue=len(selection.options),
            )
            if choice is None:
                raise SystemExit("Source selection cancelled")
            selected.append(selection.options[choice - 1])
    finally:
        root.destroy()
    return selected


def tui_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.session_id:
        return args
    args.linac = args.linac or input("Linac: ").strip()
    return args


def gui_args(args: argparse.Namespace) -> argparse.Namespace:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"tkinter is not available: {exc}")

    root = tk.Tk()
    root.withdraw()
    if not args.session_id:
        args.linac = args.linac or simpledialog.askstring("Monthly QuickCheck QA", "Linac")
    root.destroy()
    return args


def resolve_battery_check_arg(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool | None:
    if args.battery_check is not None:
        return parse_battery_check(args.battery_check)
    if not (args.practice_run or args.upload):
        return None
    if args.ui == "gui":
        return prompt_battery_check_gui()
    return prompt_battery_check_tui()


def parse_battery_check(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"good", "true", "yes", "y", "1", "pass", "ok"}:
        return True
    if normalized in {"bad", "false", "no", "n", "0", "fail"}:
        return False
    raise ValueError("--battery-check must be one of good/bad/true/false/1/0")


def prompt_battery_check_tui() -> bool:
    while True:
        raw = input("QuickCheck battery check [good/bad]: ").strip()
        try:
            return parse_battery_check(raw)
        except ValueError as exc:
            print(exc)


def prompt_battery_check_gui() -> bool:
    try:
        import tkinter as tk
        from tkinter import simpledialog
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"tkinter is not available: {exc}")

    root = tk.Tk()
    root.withdraw()
    try:
        raw = simpledialog.askstring("Monthly QuickCheck QA", "Battery check [good/bad]")
        if raw is None:
            raise SystemExit("Battery check selection cancelled")
        return parse_battery_check(raw)
    finally:
        root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a dry-run TCC Monthly QuickCheck QA payload")
    parser.add_argument("--config")
    parser.add_argument("--session-id", type=int, action="append", default=[])
    parser.add_argument("--linac")
    parser.add_argument("--date")
    parser.add_argument("--last-day", action="store_true", help="Search source sessions from the last day.")
    parser.add_argument("--last-week", action="store_true", help="Search source sessions from the last seven days.")
    parser.add_argument("--last-month", action="store_true", help="Search source sessions from the last thirty days.")
    parser.add_argument("--ui", choices=("args", "tui", "gui"), default="args")
    parser.add_argument("--battery-check", help="Battery-check result for the target QA: good/bad/true/false/1/0.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print the submission payload without uploading.")
    mode.add_argument("--practice-run", action="store_true", help="Upload to the TEST LINAC practice assignment.")
    mode.add_argument("--upload", action="store_true", help="Upload to the QuickCheck assignment resolved from serial number.")
    parser.add_argument(
        "--interactive-select",
        action="store_true",
        help="Prompt to select among duplicate matching source sessions; otherwise latest is used.",
    )
    return parser


def source_date_range(args: argparse.Namespace, today: Date | None = None) -> tuple[str, str]:
    relative_window = _selected_relative_window(args)
    if relative_window and args.date:
        raise ValueError("--date cannot be combined with --last-day, --last-week, or --last-month")

    today = today or Date.today()
    if relative_window:
        end_date = today
        start_date = end_date - timedelta(days=RELATIVE_DATE_WINDOWS[relative_window])
        return start_date.isoformat(), end_date.isoformat()

    selected_date = args.date or today.isoformat()
    return selected_date, selected_date


def _selected_relative_window(args: argparse.Namespace) -> str | None:
    selected = [
        name
        for name, enabled in (
            ("day", args.last_day),
            ("week", args.last_week),
            ("month", args.last_month),
        )
        if enabled
    ]
    if len(selected) > 1:
        raise ValueError("--last-day, --last-week, and --last-month are mutually exclusive")
    return selected[0] if selected else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.ui == "tui":
        args = tui_args(args)
    elif args.ui == "gui":
        args = gui_args(args)

    session_ids = args.session_id
    config_path = resolve_config_path(args.config)
    client = RadMachineClient(load_config(config_path))
    if session_ids:
        sessions = load_sessions_by_ids(client, session_ids)
    else:
        if not args.linac:
            parser.error("provide --linac/--date or --session-id")
        try:
            start_date, end_date = source_date_range(args)
        except ValueError as exc:
            parser.error(str(exc))
        selections = discover_source_sessions(
            client,
            args.linac,
            start_date,
            end_date,
            selected_date=args.date,
            ui=args.ui,
        )
        if args.interactive_select or args.ui in {"tui", "gui"}:
            if args.ui == "gui":
                sessions = select_source_sessions_gui(selections)
            else:
                sessions = select_source_sessions_tui(selections)
        else:
            sessions = select_latest_source_sessions(selections)

    draft = compile_quickcheck_constancy(sessions)
    try:
        battery_check = resolve_battery_check_arg(args, parser)
        if args.upload:
            _validate_submission_draft(draft)
            target_utc_id = resolve_quickcheck_target_utc_id(client, draft)
        else:
            target_utc_id = PRACTICE_TARGET_UTC_ID
        payload = build_submission_payload(draft, target_utc_id=target_utc_id, battery_check=battery_check)
    except ValueError as exc:
        parser.error(str(exc))

    output: dict[str, Any] = {
        "draft": draft.to_jsonable(),
        "mode": "dry-run",
        "payload": payload,
    }
    if args.practice_run:
        output["mode"] = "practice-run"
        if battery_check is None:
            parser.error("--battery-check is required for --practice-run")
        output["response"] = submit_practice_qa(client, draft, battery_check=battery_check)
    elif args.upload:
        output["mode"] = "upload"
        output["response"] = client.perform_qa_session(**payload)

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

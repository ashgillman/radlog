"""TCC QuickCheck constancy composite example.

This is site workflow code, not radlog library core. It gathers source QA
sessions, extracts QuickCheck and monthly solid-water output values, and builds
a dry-run payload for the target Quickcheck Constancy test.

It does not submit data to RadMachine.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date as Date
import json
from pathlib import Path
from typing import Any

from radlog.api import RadMachineClient
from radlog.config import load_config
from radlog.rm_models import TestListInstance, split_unit_name


DEFAULT_SESSION_IDS = [15073, 15074, 15079, 15078, 15077, 15076, 15075, 15091, 15093]
TARGET_UTC_ID = 111

# These order maps are deliberately kept in this example module because they
# are TCC workflow knowledge, not stable RadMachine API semantics.
PHOTON_QUICKCHECK_OUTPUT_ORDER = {
    "6 MV": 3,
    "6 FFF": 6,
    "10 MV": 12,
}
ELECTRON_QUICKCHECK_OUTPUT_ORDER = {
    "6 MeV": 3,
    "8 MeV": 8,
    "10 MeV": 13,
    "12 MeV": 18,
    "15 MeV": 23,
}
PHOTON_SOLID_WATER_DEVIATION_ORDER = 22
ELECTRON_SOLID_WATER_DEVIATION_ORDER = 12
QUICKCHECK_SERIAL_ORDER = 0

TARGET_OUTPUT_SLUGS = {
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


@dataclass(slots=True)
class ResolvedSession:
    session: TestListInstance
    collection_name: str
    unit_name: str

    @property
    def session_id(self) -> str:
        return self.session.remote_id

    @property
    def short_unit_name(self) -> str | None:
        unit, _site = split_unit_name(self.unit_name)
        return unit


@dataclass(slots=True)
class EnergyDraft:
    energy: str
    quickcheck_output: float | None = None
    solid_water_output_deviation: float | None = None
    quickcheck_session_id: str | None = None
    monthly_session_id: str | None = None


@dataclass(slots=True)
class QuickcheckConstancyDraft:
    linac: str | None
    quickcheck_serial: str | None
    target_utc_id: int = TARGET_UTC_ID
    source_session_ids: list[str] = field(default_factory=list)
    energies: dict[str, EnergyDraft] = field(default_factory=dict)
    target_values: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["energies"] = {energy: asdict(draft) for energy, draft in self.energies.items()}
        return payload


def load_sessions_by_ids(client: RadMachineClient, session_ids: list[int]) -> list[ResolvedSession]:
    return [resolve_session(client, session_id) for session_id in session_ids]


def resolve_session(client: RadMachineClient, session_id: int | str) -> ResolvedSession:
    session_payload = client.get_json(f"qa/testlistinstances/{session_id}/")
    if not isinstance(session_payload, dict):
        raise ValueError(f"Expected session object for {session_id}")
    session = TestListInstance.from_api(session_payload)

    collection_payload = client.get_json(session.unit_test_collection or "")
    if not isinstance(collection_payload, dict):
        raise ValueError(f"Expected collection object for session {session_id}")

    unit_payload = client.get_json(collection_payload.get("unit") or "")
    if not isinstance(unit_payload, dict):
        raise ValueError(f"Expected unit object for session {session_id}")

    return ResolvedSession(
        session=session,
        collection_name=str(collection_payload.get("name") or ""),
        unit_name=str(unit_payload.get("name") or ""),
    )


def find_sessions_for_linac_date(client: RadMachineClient, linac: str, performed_date: str) -> list[ResolvedSession]:
    """Find likely source sessions for a linac/date, defaulting duplicates to latest.

    This intentionally filters client-side because the exact DRF range filters
    are not documented consistently enough to bake into this example yet.
    """
    candidates: list[ResolvedSession] = []
    for session in client.qa_test_list_instances(params={"ordering": "-work_completed", "limit": "300"}):
        if not session.performed_at or session.performed_at[:10] != performed_date:
            continue
        collection_payload = client.get_json(session.unit_test_collection or "")
        if not isinstance(collection_payload, dict):
            continue
        unit_payload = client.get_json(collection_payload.get("unit") or "")
        if not isinstance(unit_payload, dict):
            continue
        resolved = ResolvedSession(
            session=session,
            collection_name=str(collection_payload.get("name") or ""),
            unit_name=str(unit_payload.get("name") or ""),
        )
        if resolved.short_unit_name == linac and _is_relevant_source_collection(resolved.collection_name):
            candidates.append(resolved)
    return _latest_session_per_collection(candidates)


def compile_quickcheck_constancy(sessions: list[ResolvedSession]) -> QuickcheckConstancyDraft:
    linacs = sorted({session.short_unit_name for session in sessions if session.short_unit_name})
    draft = QuickcheckConstancyDraft(
        linac=linacs[0] if len(linacs) == 1 else None,
        quickcheck_serial=None,
        source_session_ids=[session.session_id for session in sessions],
    )
    if len(linacs) > 1:
        draft.warnings.append(f"Multiple linacs found in source sessions: {', '.join(linacs)}")

    for session in sessions:
        collection = session.collection_name
        if collection == "Quickcheck Photons":
            _add_quickcheck_outputs(draft, session, PHOTON_QUICKCHECK_OUTPUT_ORDER)
            _add_quickcheck_serial(draft, session)
        elif collection == "Quickcheck Electrons":
            _add_quickcheck_outputs(draft, session, ELECTRON_QUICKCHECK_OUTPUT_ORDER)
            _add_quickcheck_serial(draft, session)
        elif collection.startswith("Linac Monthly :: Dosimetry :: Output and relative dosimetry :: "):
            energy = collection.rsplit(" :: ", 1)[-1]
            _add_solid_water_output(draft, session, energy, PHOTON_SOLID_WATER_DEVIATION_ORDER)
        elif collection.startswith("Linac Monthly :: Dosimetry :: Output and energy constancy :: "):
            energy = collection.rsplit(" :: ", 1)[-1]
            _add_solid_water_output(draft, session, energy, ELECTRON_SOLID_WATER_DEVIATION_ORDER)
        else:
            draft.warnings.append(f"Ignored unsupported source collection {collection!r} from session {session.session_id}")

    if draft.linac:
        draft.target_values["linac_selection"] = draft.linac
    for energy, energy_draft in draft.energies.items():
        output_slug = TARGET_OUTPUT_SLUGS.get(energy)
        if output_slug and energy_draft.quickcheck_output is not None:
            draft.target_values[output_slug] = energy_draft.quickcheck_output
        solid_water_slug = TARGET_SOLID_WATER_SLUGS.get(energy)
        if solid_water_slug and energy_draft.solid_water_output_deviation is not None:
            draft.target_values[solid_water_slug] = energy_draft.solid_water_output_deviation

    _add_missing_value_warnings(draft)
    return draft


def _add_quickcheck_outputs(draft: QuickcheckConstancyDraft, session: ResolvedSession, order_map: dict[str, int]) -> None:
    for energy, order in order_map.items():
        value = _numeric_value_at_order(session.session, order)
        if value is None:
            continue
        energy_draft = draft.energies.setdefault(energy, EnergyDraft(energy=energy))
        energy_draft.quickcheck_output = value
        energy_draft.quickcheck_session_id = session.session_id


def _add_quickcheck_serial(draft: QuickcheckConstancyDraft, session: ResolvedSession) -> None:
    serial = _string_value_at_order(session.session, QUICKCHECK_SERIAL_ORDER)
    if not serial:
        return
    if draft.quickcheck_serial and draft.quickcheck_serial != serial:
        draft.warnings.append(f"Multiple QuickCheck serials found: {draft.quickcheck_serial} and {serial}")
    draft.quickcheck_serial = serial


def _add_solid_water_output(draft: QuickcheckConstancyDraft, session: ResolvedSession, energy: str, order: int) -> None:
    value = _numeric_value_at_order(session.session, order)
    if value is None:
        return
    energy_draft = draft.energies.setdefault(energy, EnergyDraft(energy=energy))
    energy_draft.solid_water_output_deviation = value
    energy_draft.monthly_session_id = session.session_id


def _numeric_value_at_order(session: TestListInstance, order: int) -> float | None:
    test = _test_instance_at_order(session, order)
    if test is None or test.get("skipped"):
        return None
    value = test.get("value")
    if value is None:
        return None
    return float(value)


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


def _is_relevant_source_collection(name: str) -> bool:
    return (
        name in {"Quickcheck Photons", "Quickcheck Electrons"}
        or name.startswith("Linac Monthly :: Dosimetry :: Output and relative dosimetry :: ")
        or name.startswith("Linac Monthly :: Dosimetry :: Output and energy constancy :: ")
    )


def _latest_session_per_collection(sessions: list[ResolvedSession]) -> list[ResolvedSession]:
    latest: dict[str, ResolvedSession] = {}
    for session in sessions:
        current = latest.get(session.collection_name)
        if current is None or (session.session.performed_at or "") > (current.session.performed_at or ""):
            latest[session.collection_name] = session
    return list(latest.values())


def tui_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.session_id or args.default_example_sessions:
        return args
    args.linac = args.linac or input("Linac: ").strip()
    args.date = args.date or input(f"Date [{Date.today().isoformat()}]: ").strip() or Date.today().isoformat()
    return args


def gui_args(args: argparse.Namespace) -> argparse.Namespace:
    try:
        import tkinter as tk
        import tkinter.simpledialog as dialog
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(f"tkinter is not available: {exc}")

    root = tk.Tk()
    root.withdraw()
    if not args.session_id and not args.default_example_sessions:
        args.linac = args.linac or dialog.askstring("QuickCheck Constancy", "Linac")
        args.date = args.date or dialog.askstring(
            "QuickCheck Constancy",
            "Date",
            initialvalue=Date.today().isoformat(),
        )
    root.destroy()
    return args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a dry-run TCC QuickCheck constancy payload")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--session-id", type=int, action="append", default=[])
    parser.add_argument("--linac")
    parser.add_argument("--date", default=Date.today().isoformat())
    parser.add_argument("--ui", choices=("args", "tui", "gui"), default="args")
    parser.add_argument("--default-example-sessions", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.ui == "tui":
        args = tui_args(args)
    elif args.ui == "gui":
        args = gui_args(args)

    session_ids = DEFAULT_SESSION_IDS if args.default_example_sessions else args.session_id
    client = RadMachineClient(load_config(Path(args.config)))
    if session_ids:
        sessions = load_sessions_by_ids(client, session_ids)
    else:
        if not args.linac:
            parser.error("provide --linac/--date, --session-id, or --default-example-sessions")
        sessions = find_sessions_for_linac_date(client, args.linac, args.date)

    draft = compile_quickcheck_constancy(sessions)
    print(json.dumps(draft.to_jsonable(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

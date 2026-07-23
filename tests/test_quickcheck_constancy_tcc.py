from __future__ import annotations

from examples.quickcheck_constancy_tcc import (
    compile_quickcheck_constancy,
    _latest_session_per_collection,
    ResolvedSession,
)
from radlog.rm_models import TestListInstance as RmTestListInstance


def test_compile_quickcheck_constancy_builds_dry_run_target_values() -> None:
    sessions = [
        _session(
            "15091",
            "Quickcheck Photons",
            "LAx - LinacName",
            [
                {"order": 0, "string_value": "3534", "skipped": False},
                {"order": 3, "value": 99.87, "skipped": False},
                {"order": 6, "value": 100.07, "skipped": False},
                {"order": 12, "value": 99.91, "skipped": False},
            ],
        ),
        _session(
            "15093",
            "Quickcheck Electrons",
            "LAx - LinacName",
            [
                {"order": 0, "string_value": "3534", "skipped": False},
                {"order": 3, "value": 100.85, "skipped": False},
                {"order": 8, "value": 100.34, "skipped": False},
                {"order": 13, "value": 99.911, "skipped": False},
            ],
        ),
        _session(
            "15073",
            "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
            "LAx - LinacName",
            [{"order": 22, "value": 0.1179, "skipped": False}],
        ),
        _session(
            "15079",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 6 MeV",
            "LAx - LinacName",
            [{"order": 12, "value": 0.8784, "skipped": False}],
        ),
    ]

    draft = compile_quickcheck_constancy(sessions)

    assert draft.linac == "LAx"
    assert draft.quickcheck_serial == "3534"
    assert draft.target_values["linac_selection"] == "LAx"
    assert draft.target_values["quickcheck_constancy_output_6mv"] == 99.87
    assert draft.target_values["quickcheck_constancy_output_6fff"] == 100.07
    assert draft.target_values["quickcheck_constancy_output_10mv"] == 99.91
    assert draft.target_values["quickcheck_constancy_output_6mev"] == 100.85
    assert draft.target_values["quickcheck_constancy_solid_water_output_6mv"] == 0.1179
    assert draft.target_values["quickcheck_constancy_solid_water_output_6mev"] == 0.8784


def test_compile_quickcheck_constancy_warns_on_multiple_quickchecks() -> None:
    sessions = [
        _session(
            "1",
            "Quickcheck Photons",
            "LAx - LinacName",
            [{"order": 0, "string_value": "3534", "skipped": False}],
        ),
        _session(
            "2",
            "Quickcheck Electrons",
            "LAx - LinacName",
            [{"order": 0, "string_value": "9999", "skipped": False}],
        ),
    ]

    draft = compile_quickcheck_constancy(sessions)

    assert "Multiple QuickCheck serials found: 3534 and 9999" in draft.warnings


def test_latest_session_per_collection_defaults_to_last_session() -> None:
    old = _session("1", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T10:00:00+10:00")
    new = _session("2", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T11:00:00+10:00")

    assert _latest_session_per_collection([old, new]) == [new]


def _session(
    remote_id: str,
    collection_name: str,
    unit_name: str,
    test_instances: list[dict],
    performed_at: str = "2026-07-07T10:00:00+10:00",
) -> ResolvedSession:
    return ResolvedSession(
        session=RmTestListInstance.from_api(
            {
                "url": f"https://radmachine.example/demo-customer/api/qa/testlistinstances/{remote_id}/",
                "work_completed": performed_at,
                "test_instances": test_instances,
            }
        ),
        collection_name=collection_name,
        unit_name=unit_name,
    )

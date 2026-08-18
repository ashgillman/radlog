from __future__ import annotations

import argparse
from datetime import date as Date
import json
from unittest.mock import patch

from examples.quickcheck_constancy_tcc import (
    EnergyDraft,
    PRACTICE_TARGET_UTC_ID,
    QuickcheckConstancyDraft,
    build_submission_payload,
    compile_quickcheck_constancy,
    discover_quickcheck_source_sessions,
    discover_source_sessions,
    main,
    parse_battery_check,
    resolve_quickcheck_target_utc_id,
    source_date_range,
    select_latest_source_sessions,
    select_source_sessions_tui,
    _submission_comment,
    _source_selections,
    ResolvedSession,
)
from radlog.rm_models import TestListInstance as RmTestListInstance
from radlog.rm_models import Unit, UnitTestCollection


def test_compile_quickcheck_constancy_builds_dry_run_target_values() -> None:
    sessions = [
        _session(
            "15091",
            "Quickcheck Photons",
            "LAx - LinacName",
            [
                {"order": 0, "string_value": "3534", "skipped": False},
                {"order": 3, "value": 99.87, "skipped": False},
                {"order": 6, "value": 100.07, "skipped": True},
                {"order": 12, "value": 99.91, "skipped": False},
                {"order": 30, "value": 100.42, "skipped": False},
            ],
            test_slugs_by_order={
                3: "quickcheck_cax_output_6_mv",
                6: "quickcheck_cax_output_6_mv_fff",
                12: "quickcheck_symmetry_lr_10_mv",
                30: "quickcheck_cax_output_10_mv",
            },
            work_started="2026-07-07T11:00:00+10:00",
            work_completed="2026-07-07T11:05:00+10:00",
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
            test_slugs_by_order={
                3: "quickcheck_cax_output_6_mev",
                8: "quickcheck_cax_output_8_mev",
                13: "quickcheck_cax_output_10_mev",
            },
            work_started="2026-07-07T11:10:00+10:00",
            work_completed="2026-07-07T11:20:00+10:00",
        ),
        _session(
            "15073",
            "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
            "LAx - LinacName",
            [
                {"order": 22, "value": 9.999, "skipped": False},
                {"order": 30, "value": 0.1179, "skipped": False},
            ],
            test_slugs_by_order={22: "sliding_window", 30: "linac_monthly_output_deviation_6_mv"},
            work_started="2026-07-07T08:00:00+10:00",
            work_completed="2026-07-07T08:45:00+10:00",
        ),
        _session(
            "15079",
            "Linac Monthly :: Dosimetry :: Output and energy constancy :: 6 MeV",
            "LAx - LinacName",
            [{"order": 30, "value": 0.8784, "skipped": False}],
            test_slugs_by_order={30: "linac_monthly_output_deviation_6_mev"},
            work_started="2026-07-07T09:00:00+10:00",
            work_completed="2026-07-07T12:00:00+10:00",
        ),
    ]

    draft = compile_quickcheck_constancy(sessions)

    assert draft.linac == "LAx"
    assert draft.quickcheck_serial == "3534"
    assert draft.work_started == "2026-07-07T08:00:00+10:00"
    assert draft.work_completed == "2026-07-07T12:00:00+10:00"
    assert draft.target_values["linac_selection"] == "LAx"
    assert draft.target_values["work_started"] == "2026-07-07T08:00:00+10:00"
    assert draft.target_values["work_completed"] == "2026-07-07T12:00:00+10:00"
    assert draft.target_values["quickcheck_constancy_output_6mv"] == 99.87
    assert "quickcheck_constancy_output_6fff" not in draft.target_values
    assert draft.target_values["quickcheck_constancy_output_10mv"] == 100.42
    assert draft.target_values["quickcheck_constancy_output_6mev"] == 100.85
    assert draft.target_values["quickcheck_constancy_solid_water_output_6mv"] == 0.1179
    assert draft.target_values["quickcheck_constancy_solid_water_output_6mev"] == 0.8784
    assert draft.energies["6 MV"].quickcheck_url == "https://radmachine.example/demo-customer/qa/session/details/15091/"
    assert draft.energies["6 MV"].monthly_url == "https://radmachine.example/demo-customer/qa/session/details/15073/"
    assert draft.energies["6 MV"].quickcheck_work_started == "2026-07-07T11:00:00+10:00"
    assert draft.energies["6 MV"].quickcheck_work_completed == "2026-07-07T11:05:00+10:00"
    assert draft.energies["6 MV"].monthly_work_started == "2026-07-07T08:00:00+10:00"
    assert draft.energies["6 MV"].monthly_work_completed == "2026-07-07T08:45:00+10:00"
    assert draft.to_jsonable()["energies"]["6 MV"]["quickcheck_url"] == (
        "https://radmachine.example/demo-customer/qa/session/details/15091/"
    )


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


def test_build_submission_payload_uses_practice_assignment_and_source_comment() -> None:
    draft = QuickcheckConstancyDraft(
        linac="LAx",
        quickcheck_serial="3534",
        work_started="2026-07-07T08:00:00+10:00",
        work_completed="2026-07-07T12:00:00+10:00",
        energies={
            "6 MV": EnergyDraft(
                energy="6 MV",
                quickcheck_output=99.87,
                solid_water_output_deviation=0.1179,
                quickcheck_session_id="15091",
                quickcheck_url="https://radmachine.example/demo-customer/qa/session/details/15091/",
                monthly_session_id="15073",
                monthly_url="https://radmachine.example/demo-customer/qa/session/details/15073/",
            ),
            "6 FFF": EnergyDraft(
                energy="6 FFF",
                quickcheck_session_id="15091",
                quickcheck_url="https://radmachine.example/demo-customer/qa/session/details/15091/",
            ),
            "10 MV": EnergyDraft(
                energy="10 MV",
                quickcheck_output=100.42,
                solid_water_output_deviation=0.1369,
            ),
        },
        target_values={
            "linac_selection": "LAx",
            "quickcheck_constancy_output_10mv": 100.42,
            "quickcheck_constancy_solid_water_output_10mv": 0.1369,
            "quickcheck_constancy_output_6mv": 99.87,
            "quickcheck_constancy_solid_water_output_6mv": 0.1179,
            "work_started": "2026-07-07T08:00:00+10:00",
            "work_completed": "2026-07-07T12:00:00+10:00",
        },
    )

    payload = build_submission_payload(draft, battery_check=True)

    assert payload["unit_test_collection"] == PRACTICE_TARGET_UTC_ID
    assert payload["work_started"] == "2026-07-07T08:00:00+10:00"
    assert payload["work_completed"] == "2026-07-07T12:00:00+10:00"
    assert payload["tests"] == {
        "linac_selection": {"value": "LAx"},
        "quickcheck_battery_check": {"value": True},
        "quickcheck_constancy_output_10mev": {"skipped": True},
        "quickcheck_constancy_output_10mv": {"value": 100.42},
        "quickcheck_constancy_output_12mev": {"skipped": True},
        "quickcheck_constancy_output_15mev": {"skipped": True},
        "quickcheck_constancy_output_6fff": {"skipped": True},
        "quickcheck_constancy_output_6mev": {"skipped": True},
        "quickcheck_constancy_output_6mv": {"value": 99.87},
        "quickcheck_constancy_output_8mev": {"skipped": True},
        "quickcheck_constancy_solid_water_output_10mev": {"skipped": True},
        "quickcheck_constancy_solid_water_output_10mv": {"value": 0.1369},
        "quickcheck_constancy_solid_water_output_12mev": {"skipped": True},
        "quickcheck_constancy_solid_water_output_15mev": {"skipped": True},
        "quickcheck_constancy_solid_water_output_6fff": {"skipped": True},
        "quickcheck_constancy_solid_water_output_6mev": {"skipped": True},
        "quickcheck_constancy_solid_water_output_6mv": {"value": 0.1179},
        "quickcheck_constancy_solid_water_output_8mev": {"skipped": True},
    }
    assert "quickcheck_constancy_output_difference_6_mv_fff" not in payload["tests"]
    assert "2026-07-07T08:00:00+10:00" not in payload["tests"]
    assert "QuickCheck serial: 3534" in payload["comment"]
    assert "https://radmachine.example/demo-customer/qa/session/details/15091/" in payload["comment"]


def test_build_submission_payload_rejects_mixed_quickcheck_serials() -> None:
    draft = QuickcheckConstancyDraft(
        linac="LAx",
        quickcheck_serial="3534",
        work_started="2026-07-07T08:00:00+10:00",
        work_completed="2026-07-07T12:00:00+10:00",
        energies={
            "6 MV": EnergyDraft("6 MV", quickcheck_output=99.87, solid_water_output_deviation=0.1179),
            "10 MV": EnergyDraft("10 MV", quickcheck_output=100.42, solid_water_output_deviation=0.1369),
        },
        target_values={
            "quickcheck_constancy_output_6mv": 99.87,
            "quickcheck_constancy_solid_water_output_6mv": 0.1179,
            "quickcheck_constancy_output_10mv": 100.42,
            "quickcheck_constancy_solid_water_output_10mv": 0.1369,
        },
        warnings=["Multiple QuickCheck serials found: 3534 and 9999"],
    )

    try:
        build_submission_payload(draft)
    except ValueError as exc:
        assert "Multiple QuickCheck serials found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_submission_comment_groups_sources_by_modality_and_numeric_energy() -> None:
    photon_qc_url = "https://radmachine.example/tcc/qa/session/details/15741/"
    electron_qc_url = "https://radmachine.example/tcc/qa/session/details/15746/"
    draft = QuickcheckConstancyDraft(
        linac="LA7",
        quickcheck_serial="3534",
        energies={
            "15 MeV": EnergyDraft(
                "15 MeV",
                monthly_session_id="15730",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15730/",
            ),
            "10 MV": EnergyDraft(
                "10 MV",
                quickcheck_session_id="15741",
                quickcheck_url=photon_qc_url,
                monthly_session_id="15729",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15729/",
            ),
            "6 MV": EnergyDraft(
                "6 MV",
                quickcheck_session_id="15741",
                quickcheck_url=photon_qc_url,
                monthly_session_id="15728",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15728/",
            ),
            "12 MeV": EnergyDraft(
                "12 MeV",
                monthly_session_id="15731",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15731/",
            ),
            "10 MeV": EnergyDraft(
                "10 MeV",
                quickcheck_session_id="15746",
                quickcheck_url=electron_qc_url,
                monthly_session_id="15732",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15732/",
            ),
            "6 MeV": EnergyDraft(
                "6 MeV",
                quickcheck_session_id="15746",
                quickcheck_url=electron_qc_url,
                monthly_session_id="15733",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15733/",
            ),
            "8 MeV": EnergyDraft(
                "8 MeV",
                monthly_session_id="15734",
                monthly_url="https://radmachine.example/tcc/qa/session/details/15734/",
            ),
        },
    )

    assert _submission_comment(draft) == """Compiled by radlog from source QA.
QuickCheck serial: 3534

Source sessions:
MV QuickCheck: https://radmachine.example/tcc/qa/session/details/15741/
6 MV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15728/
10 MV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15729/
MeV QuickCheck: https://radmachine.example/tcc/qa/session/details/15746/
6 MeV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15733/
8 MeV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15734/
10 MeV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15732/
12 MeV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15731/
15 MeV Monthly dosimetry: https://radmachine.example/tcc/qa/session/details/15730/"""


def test_parse_battery_check_accepts_expected_aliases() -> None:
    assert parse_battery_check("good") is True
    assert parse_battery_check("true") is True
    assert parse_battery_check("1") is True
    assert parse_battery_check("bad") is False
    assert parse_battery_check("false") is False
    assert parse_battery_check("0") is False


def test_build_submission_payload_rejects_missing_required_photon_values() -> None:
    draft = QuickcheckConstancyDraft(
        linac="LAx",
        quickcheck_serial="3534",
        work_started="2026-07-07T08:00:00+10:00",
        work_completed="2026-07-07T12:00:00+10:00",
        energies={"6 MV": EnergyDraft("6 MV", quickcheck_output=99.87, solid_water_output_deviation=0.1179)},
        target_values={"quickcheck_constancy_output_6mv": 99.87},
    )

    try:
        build_submission_payload(draft)
    except ValueError as exc:
        assert "Missing required QuickCheck output for 10 MV" in str(exc)
        assert "Missing required monthly solid-water output deviation for 10 MV" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_resolve_quickcheck_target_utc_id_uses_serial_unit_and_test_list_name(monkeypatch) -> None:
    calls = []

    def fake_collect(_client, **kwargs):
        calls.append(kwargs)
        return [UnitTestCollection.from_api({"url": "https://radmachine.example/api/qa/unittestcollections/321/"})]

    monkeypatch.setattr("examples.quickcheck_constancy_tcc.collect_unit_test_collections", fake_collect)
    draft = QuickcheckConstancyDraft(linac="LAx", quickcheck_serial="3534")

    assert resolve_quickcheck_target_utc_id(object(), draft) == 321
    assert calls[0]["unit"] == "PTW Quickcheck: 3534"
    assert calls[0]["collection_name_matches"]("Quickcheck Constancy")
    assert not calls[0]["collection_name_matches"]("Daily QuickCheck")


def test_source_selections_preserve_duplicates_latest_first() -> None:
    old = _session("1", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T10:00:00+10:00")
    new = _session("2", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T11:00:00+10:00")

    selections = _source_selections([old, new])

    assert len(selections) == 1
    assert selections[0].role == "quickcheck_photons"
    assert [option.session_id for option in selections[0].options] == ["2", "1"]
    assert [session.session_id for session in select_latest_source_sessions(selections)] == ["2"]


def test_tui_selection_can_override_latest_default(monkeypatch, capsys) -> None:
    old = _session("1", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T10:00:00+10:00")
    new = _session("2", "Quickcheck Photons", "LAx - LinacName", [], performed_at="2026-07-07T11:00:00+10:00")
    selections = _source_selections([old, new])
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    selected = select_source_sessions_tui(selections)

    assert [session.session_id for session in selected] == ["1"]
    assert "Daily QuickCheck photons" in capsys.readouterr().out


def test_discover_source_sessions_queries_monthly_first_then_same_day_quickcheck(monkeypatch) -> None:
    monthly_old = _session(
        "10",
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 6 MV",
        "LAx - LinacName",
        [],
        performed_at="2026-07-07T10:00:00+10:00",
    )
    monthly_new = _session(
        "11",
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
        "LAx - LinacName",
        [],
        performed_at="2026-07-08T10:00:00+10:00",
    )
    quickcheck = _session(
        "12",
        "Quickcheck Photons",
        "LAx - LinacName",
        [],
        performed_at="2026-07-08T11:00:00+10:00",
    )
    calls = []

    def fake_monthly(_client, linac, start_date, end_date):
        calls.append(("monthly", linac, start_date, end_date))
        return [monthly_old, monthly_new]

    def fake_quickcheck(_client, linac, performed_date):
        calls.append(("quickcheck", linac, performed_date))
        return [quickcheck]

    monkeypatch.setattr("examples.quickcheck_constancy_tcc.discover_monthly_source_sessions", fake_monthly)
    monkeypatch.setattr("examples.quickcheck_constancy_tcc.discover_quickcheck_source_sessions", fake_quickcheck)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    selections = discover_source_sessions(object(), "LAx", "2026-07-01", "2026-07-31")

    assert calls == [
        ("monthly", "LAx", "2026-07-01", "2026-07-31"),
        ("quickcheck", "LAx", "2026-07-08"),
    ]
    assert [selection.role for selection in selections] == ["quickcheck_photons", "monthly_photon_10 MV"]


def test_discover_source_sessions_reports_missing_quickcheck_photons(monkeypatch) -> None:
    monthly = _session(
        "11",
        "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
        "LA7 - Hayman",
        [],
        performed_at="2026-08-16T10:00:00+10:00",
    )
    monkeypatch.setattr(
        "examples.quickcheck_constancy_tcc.discover_monthly_source_sessions",
        lambda *_args, **_kwargs: [monthly],
    )
    monkeypatch.setattr(
        "examples.quickcheck_constancy_tcc.discover_quickcheck_source_sessions",
        lambda *_args, **_kwargs: [],
    )

    try:
        discover_source_sessions(
            object(),
            "LA7",
            "2026-08-16",
            "2026-08-16",
            selected_date="2026-08-16",
        )
    except SystemExit as exc:
        message = str(exc)
        assert "No QuickCheck photon source session found for LA7 on 2026-08-16" in message
        assert "perform or register QuickCheck QA" in message
    else:
        raise AssertionError("expected SystemExit")


def test_discover_quickcheck_source_sessions_attaches_test_slugs(monkeypatch) -> None:
    quickcheck = _session(
        "12",
        "Quickcheck Photons",
        "LAx - LinacName",
        [{"order": 14, "value": None, "skipped": True}],
    )
    calls = []

    def fake_collect_collections(*_args, **kwargs):
        calls.append(("collections", kwargs["unit"]))
        return [object()]

    def fake_collect_sessions(*_args, **kwargs):
        calls.append(("sessions", kwargs["start"], kwargs["end"]))
        return [quickcheck]

    def fake_attach(_client, sessions):
        calls.append([session.session_id for session in sessions])
        sessions[0].session.raw["_radlog_test_slugs_by_order"] = {14: "quickcheck_cax_output_6_mv_fff"}

    monkeypatch.setattr("examples.quickcheck_constancy_tcc.collect_unit_test_collections", fake_collect_collections)
    monkeypatch.setattr("examples.quickcheck_constancy_tcc.collect_resolved_qa_sessions_for_collections", fake_collect_sessions)
    monkeypatch.setattr("examples.quickcheck_constancy_tcc.attach_test_definition_slugs", fake_attach)

    sessions = discover_quickcheck_source_sessions(object(), "LAx", "2026-07-08")

    assert calls == [("collections", "LAx"), ("sessions", "2026-07-08", "2026-07-08"), ["12"]]
    assert sessions[0].session.raw["_radlog_test_slugs_by_order"] == {14: "quickcheck_cax_output_6_mv_fff"}


def test_main_uses_default_config_discovery_when_config_not_provided(capsys) -> None:
    draft = QuickcheckConstancyDraft(
        linac="LAx",
        quickcheck_serial="3534",
        work_started="2026-07-07T08:00:00+10:00",
        work_completed="2026-07-07T12:00:00+10:00",
        energies={
            "6 MV": EnergyDraft("6 MV", quickcheck_output=99.87, solid_water_output_deviation=0.1179),
            "10 MV": EnergyDraft("10 MV", quickcheck_output=100.42, solid_water_output_deviation=0.1369),
        },
        target_values={
            "quickcheck_constancy_output_6mv": 99.87,
            "quickcheck_constancy_solid_water_output_6mv": 0.1179,
            "quickcheck_constancy_output_10mv": 100.42,
            "quickcheck_constancy_solid_water_output_10mv": 0.1369,
        },
    )
    with (
        patch("examples.quickcheck_constancy_tcc.resolve_config_path", return_value="resolved-config.toml") as resolve,
        patch("examples.quickcheck_constancy_tcc.load_config", return_value=object()) as load,
        patch("examples.quickcheck_constancy_tcc.RadMachineClient"),
        patch("examples.quickcheck_constancy_tcc.load_sessions_by_ids", return_value=[]),
        patch("examples.quickcheck_constancy_tcc.compile_quickcheck_constancy", return_value=draft),
    ):
        exit_code = main(["--session-id", "15091"])

    assert exit_code == 0
    resolve.assert_called_once_with(None)
    load.assert_called_once_with("resolved-config.toml")
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry-run"
    assert output["payload"]["unit_test_collection"] == PRACTICE_TARGET_UTC_ID
    assert output["payload"]["tests"]["quickcheck_battery_check"] == {"skipped": True}
    assert output["payload"]["tests"]["quickcheck_constancy_output_6mv"] == {"value": 99.87}
    assert output["payload"]["tests"]["quickcheck_constancy_output_10mv"] == {"value": 100.42}


def test_main_practice_run_uploads_to_practice_assignment(capsys) -> None:
    draft = QuickcheckConstancyDraft(
        linac="LAx",
        quickcheck_serial="3534",
        work_started="2026-07-07T08:00:00+10:00",
        work_completed="2026-07-07T12:00:00+10:00",
        energies={
            "6 MV": EnergyDraft("6 MV", quickcheck_output=99.87, solid_water_output_deviation=0.1179),
            "10 MV": EnergyDraft("10 MV", quickcheck_output=100.42, solid_water_output_deviation=0.1369),
        },
        target_values={
            "quickcheck_constancy_output_6mv": 99.87,
            "quickcheck_constancy_solid_water_output_6mv": 0.1179,
            "quickcheck_constancy_output_10mv": 100.42,
            "quickcheck_constancy_solid_water_output_10mv": 0.1369,
        },
    )
    client = object()
    with (
        patch("examples.quickcheck_constancy_tcc.resolve_config_path", return_value="resolved-config.toml"),
        patch("examples.quickcheck_constancy_tcc.load_config", return_value=object()),
        patch("examples.quickcheck_constancy_tcc.RadMachineClient", return_value=client),
        patch("examples.quickcheck_constancy_tcc.load_sessions_by_ids", return_value=[]),
        patch("examples.quickcheck_constancy_tcc.compile_quickcheck_constancy", return_value=draft),
        patch("examples.quickcheck_constancy_tcc.submit_practice_qa", return_value={"url": "created"}) as submit,
    ):
        exit_code = main(["--session-id", "15091", "--practice-run", "--battery-check", "good"])

    assert exit_code == 0
    submit.assert_called_once_with(client, draft, battery_check=True)
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "practice-run"
    assert output["response"] == {"url": "created"}


def test_source_date_range_accepts_standard_relative_windows() -> None:
    args = argparse.Namespace(date=None, last_day=False, last_week=True, last_month=False)

    assert source_date_range(args, today=Date(2026, 7, 30)) == ("2026-07-23", "2026-07-30")


def test_source_date_range_rejects_ambiguous_relative_windows() -> None:
    args = argparse.Namespace(date=None, last_day=False, last_week=True, last_month=True)

    try:
        source_date_range(args, today=Date(2026, 7, 30))
    except ValueError as exc:
        assert "--last-day, --last-week, and --last-month are mutually exclusive" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_source_date_range_rejects_date_with_relative_window() -> None:
    args = argparse.Namespace(date="2026-07-07", last_day=False, last_week=True, last_month=False)

    try:
        source_date_range(args, today=Date(2026, 7, 30))
    except ValueError as exc:
        assert "--date cannot be combined" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _session(
    remote_id: str,
    collection_name: str,
    unit_name: str,
    test_instances: list[dict],
    performed_at: str = "2026-07-07T10:00:00+10:00",
    work_started: str | None = None,
    work_completed: str | None = None,
    test_slugs_by_order: dict[int, str] | None = None,
) -> ResolvedSession:
    work_completed = work_completed or performed_at
    raw = {
        "url": f"https://radmachine.example/demo-customer/api/qa/testlistinstances/{remote_id}/",
        "site_url": f"https://radmachine.example/demo-customer/qa/session/details/{remote_id}/",
        "work_started": work_started,
        "work_completed": work_completed,
        "test_instances": test_instances,
    }
    if test_slugs_by_order:
        raw["_radlog_test_slugs_by_order"] = test_slugs_by_order
    return ResolvedSession(
        session=RmTestListInstance.from_api(raw),
        collection=UnitTestCollection.from_api({"name": collection_name}),
        unit=Unit.from_api({"name": unit_name}),
    )

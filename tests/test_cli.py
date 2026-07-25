from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

from radlog.cli import main
from radlog.models import CandidateEntry
from radlog.report_models import AbnormalQaReport, QaIssue
from radlog.rm_models import ServiceEvent
from radlog.rm_models import TestListInstance as RmTestListInstance
from tests.support import TEST_BASE_URL, TEST_CUSTOMER_ID


def test_cli_emits_json_payload(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "default-user"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch("radlog.cli.RadMachineClient.get_json", return_value={"qa": "endpoint"}) as get_json:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--start",
                "2026-03-01",
                "--end",
                "2026-03-31",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["start"] == "2026-03-01"
    assert payload["end"] == "2026-03-31"
    assert payload["user"] == "default-user"
    assert payload["endpoint"] == "/"
    assert payload["server"] == {"qa": "endpoint"}
    assert payload["records"] is None
    assert payload["candidates"] == []
    get_json.assert_called_once_with("", params={})


def test_cli_reports_missing_config(capsys) -> None:
    exit_code = main(["--config", "does-not-exist.toml"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "Config file not found" in captured.err


def test_cli_uses_default_user_config_path(capsys, tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config-home" / "radlog"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch("radlog.cli.RadMachineClient.get_json", return_value={"qa": "endpoint"}):
        exit_code = main([])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] == {"qa": "endpoint"}


def test_cli_accepts_direct_config_token(capsys, tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "default-user"
token = "secret-token"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    with patch("radlog.cli.RadMachineClient.get_json", return_value={"qa": "endpoint"}):
        exit_code = main(["--config", str(config_file)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["config"]["radmachine"]["token"] == "<redacted>"
    assert "secret-token" not in captured.out


def test_cli_validates_report_filters_before_config_load(capsys) -> None:
    exit_code = main(
        [
            "--config",
            "does-not-exist.toml",
            "--report",
            "abnormal-qa",
            "--filter-by-results",
            "bogus",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "Unknown --filter-by-results value" in captured.err


def test_cli_reports_missing_token(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.delenv("RADMACHINE_TOKEN", raising=False)

    exit_code = main(["--config", str(config_file)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "RADMACHINE_TOKEN" in captured.err


def test_cli_uses_pagination_when_requested(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch("radlog.cli.RadMachineClient.paginate", return_value=iter([{"id": 1}, {"id": 2}])) as paginate:
        exit_code = main(["--config", str(config_file), "--endpoint", "qa/", "--paginate"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] == [{"id": 1}, {"id": 2}]
    assert payload["records"] is None
    paginate.assert_called_once_with("qa/", params={})


def test_cli_exports_named_endpoint_as_raw_payloads(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    raw_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/13162/",
        "work_completed": "2026-03-06T10:10:00+10:00",
        "unexpected": "preserved",
    }

    with patch(
        "radlog.cli.RadMachineClient.qa_test_list_instances",
        return_value=iter([RmTestListInstance.from_api(raw_payload)]),
    ) as export_raw:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--export-raw",
                "qa-testlistinstances",
                "--limit",
                "1",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] is None
    assert payload["raw_export"] == [raw_payload]
    export_raw.assert_called_once_with(params={"limit": "1", "ordering": "-work_completed"})


def test_cli_export_raw_applies_date_range_and_default_ordering(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    old_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/1/",
        "work_completed": "2026-03-01T10:00:00+10:00",
    }
    selected_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/2/",
        "work_completed": "2026-03-06T10:00:00+10:00",
    }
    new_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/qa/testlistinstances/3/",
        "work_completed": "2026-03-20T10:00:00+10:00",
    }

    with patch(
        "radlog.cli.RadMachineClient.qa_test_list_instances",
        return_value=iter(
            [
                RmTestListInstance.from_api(new_payload),
                RmTestListInstance.from_api(selected_payload),
                RmTestListInstance.from_api(old_payload),
            ]
        ),
    ) as export_raw:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--export-raw",
                "qa-testlistinstances",
                "--start",
                "2026-03-05",
                "--end",
                "2026-03-10",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["raw_export"] == [selected_payload]
    export_raw.assert_called_once_with(params={"ordering": "-work_completed"})


def test_cli_export_raw_preserves_explicit_ordering(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch("radlog.cli.RadMachineClient.service_events", return_value=iter([])) as export_raw:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--export-raw",
                "service-events",
                "--param",
                "ordering=datetime_service",
            ]
        )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["raw_export"] == []
    export_raw.assert_called_once_with(params={"ordering": "datetime_service"})


def test_cli_export_raw_dates_service_events(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    selected_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/324/",
        "datetime_service": "2026-04-14T14:46:00+10:00",
    }
    old_payload = {
        "url": f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/api/servicelog/serviceevents/323/",
        "datetime_service": "2026-03-01T14:46:00+10:00",
    }

    with patch(
        "radlog.cli.RadMachineClient.service_events",
        return_value=iter([ServiceEvent.from_api(selected_payload), ServiceEvent.from_api(old_payload)]),
    ) as export_raw:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--export-raw",
                "service-events",
                "--start",
                "2026-04-01",
                "--end",
                "2026-04-30",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["raw_export"] == [selected_payload]
    export_raw.assert_called_once_with(params={"ordering": "-datetime_service"})


def test_cli_export_raw_rejects_dates_for_units(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--export-raw",
            "units",
            "--start",
            "2026-03-01",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "--start/--end are not supported for --export-raw units" in captured.err


def test_cli_rejects_collect_with_raw_export(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--collect",
            "qa-sessions",
            "--export-raw",
            "qa-testlistinstances",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "--export-raw cannot be combined with --collect" in captured.err


def test_cli_reports_abnormal_qa_as_json(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    report = AbnormalQaReport(
        start="2026-07-14",
        end="2026-07-21",
        issues=[
            _issue("action", "Failing geometry", comment="Investigated and repeated."),
            _issue("tolerance", "Near tolerance"),
            _issue("comment", "Comment only", comment="Please review trend."),
        ],
    )

    with patch("radlog.cli.collect_abnormal_qa_report", return_value=report) as collect:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--report",
                "abnormal-qa",
                "--start",
                "2026-07-14",
                "--end",
                "2026-07-21",
                "--filter-by-results",
                "action,tol",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["report"]["start"] == "2026-07-14"
    assert payload["report"]["end"] == "2026-07-21"
    assert [issue["issue_type"] for issue in payload["report"]["issues"]] == ["action", "tolerance"]
    assert payload["server"] is None
    assert payload["records"] is None
    assert payload["candidates"] == []
    collect.assert_called_once()


def test_cli_filters_abnormal_qa_with_where_expression(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    report = AbnormalQaReport(
        start="2026-07-14",
        end="2026-07-21",
        issues=[
            _issue("action", "Failing geometry", equipment_name="LAx"),
            _issue("tolerance", "Near tolerance", equipment_name="LAx"),
            _issue("action", "CT action", equipment_name="CTx"),
            _issue("comment", "Comment only", equipment_name="LAx", comment="Please review trend."),
        ],
    )

    with patch("radlog.cli.collect_abnormal_qa_report", return_value=report):
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--report",
                "abnormal-qa",
                "--start",
                "2026-07-14",
                "--end",
                "2026-07-21",
                "--filter-by-results",
                "all",
                "--where",
                "( issue = action -o issue = tolerance ) -and equipment = LAx",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert [issue["test_label"] for issue in payload["report"]["issues"]] == ["Failing geometry", "Near tolerance"]


def test_cli_reports_invalid_where_expression_before_config_load(capsys) -> None:
    exit_code = main(["--config", "does-not-exist.toml", "--report", "abnormal-qa", "--where", "unknown = value"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "Unknown report filter field" in captured.err


def test_cli_defaults_abnormal_qa_report_to_last_week(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 24)

    monkeypatch.setattr("radlog.cli.Date", FakeDate)
    report = AbnormalQaReport(start="2026-07-17", end="2026-07-24", issues=[])

    with patch("radlog.cli.collect_abnormal_qa_report", return_value=report) as collect:
        exit_code = main(["--config", str(config_file), "--report", "abnormal-qa"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    collect.assert_called_once()
    assert collect.call_args.kwargs["start"] == "2026-07-17"
    assert collect.call_args.kwargs["end"] == "2026-07-24"
    assert payload["start"] == "2026-07-17"
    assert payload["end"] == "2026-07-24"


def test_cli_accepts_last_week_date_window(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 24)

    monkeypatch.setattr("radlog.cli.Date", FakeDate)
    report = AbnormalQaReport(start="2026-07-17", end="2026-07-24", issues=[])

    with patch("radlog.cli.collect_abnormal_qa_report", return_value=report) as collect:
        exit_code = main(["--config", str(config_file), "--report", "abnormal-qa", "--last-week"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert collect.call_args.kwargs["start"] == "2026-07-17"
    assert collect.call_args.kwargs["end"] == "2026-07-24"
    assert payload["start"] == "2026-07-17"
    assert payload["end"] == "2026-07-24"


def test_cli_rejects_relative_date_window_with_explicit_dates(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--report",
            "abnormal-qa",
            "--last-week",
            "--start",
            "2026-07-14",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "cannot be combined with --start or --end" in captured.err


def test_cli_rejects_multiple_relative_date_windows(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(["--config", str(config_file), "--report", "abnormal-qa", "--last-week", "--last-month"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "mutually exclusive" in captured.err


def test_cli_prints_abnormal_qa_profile_to_stderr(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    def collect_report(*args, **kwargs):
        profile = kwargs["profile"]
        profile.sessions_seen = 12
        profile.sessions_in_range = 8
        profile.sessions_with_issues = 3
        profile.metadata_fetches = 15
        profile.metadata_fetches_by_kind["qa/testlists-details"] = 6
        profile.metadata_fetches_by_kind["units/units"] = 2
        profile.metadata_cache_hits = 4
        profile.test_lists_flattened = 5
        profile.seconds_paginating = 1.2
        profile.seconds_metadata = 3.4
        profile.seconds_flattening = 2.5
        return AbnormalQaReport(start="2026-07-14", end="2026-07-21", issues=[])

    with patch("radlog.cli.collect_abnormal_qa_report", side_effect=collect_report):
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--report",
                "abnormal-qa",
                "--start",
                "2026-07-14",
                "--end",
                "2026-07-21",
                "--profile",
            ]
        )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Abnormal QA collection profile:" in captured.err
    assert "sessions_seen: 12" in captured.err
    assert "metadata_fetches: 15" in captured.err
    assert "qa/testlists-details: 6" in captured.err
    assert "units/units: 2" in captured.err
    assert "seconds_metadata: 3.400" in captured.err


def test_cli_reports_abnormal_qa_as_plaintext(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    report = AbnormalQaReport(
        start="2026-07-14",
        end="2026-07-21",
        issues=[
            _issue("action", "Failing geometry", comment="Investigated and repeated."),
            _issue("comment", "Comment only", comment="Please review trend."),
        ],
    )

    with patch("radlog.cli.collect_abnormal_qa_report", return_value=report):
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--report",
                "abnormal-qa",
                "--start",
                "2026-07-14",
                "--end",
                "2026-07-21",
                "--filter-by-results",
                "action,comment",
                "--render",
                "plaintext",
            ]
        )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Abnormal QA Report: 2026-07-14 to 2026-07-21" in captured.out
    assert "LINAC-A" in captured.out
    assert "Failing geometry" in captured.out
    assert "Investigated and repeated." in captured.out
    assert "Comment only" in captured.out
    assert captured.err == ""


def test_cli_rejects_report_with_collect(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(
        [
            "--config",
            str(config_file),
            "--collect",
            "qa-sessions",
            "--report",
            "abnormal-qa",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--report cannot be combined with --collect or --export-raw" in captured.err


def test_cli_supports_custom_query_params(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch("radlog.cli.RadMachineClient.get_json", return_value={"ok": True}) as get_json:
        exit_code = main(
            [
                "--config",
                str(config_file),
                "--endpoint",
                "qa/testinstances",
                "--limit",
                "2",
                "--offset",
                "10",
                "--param",
                "created_by__username=example-user",
            ]
        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] == {"ok": True}
    get_json.assert_called_once_with(
        "qa/testinstances",
        params={"limit": "2", "offset": "10", "created_by__username": "example-user"},
    )


def test_cli_collects_qa_sessions(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "default-user"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    with patch(
        "radlog.cli.collect_qa_sessions",
        return_value=[
            {
                "source_type": "qa_session",
                "remote_id": "13162",
                "title": "Linac Monthly :: Dosimetry :: Output and relative dosimetry :: 10 MV",
            }
        ],
    ):
        with patch("radlog.cli.serialize_source_records", return_value=[{"remote_id": "13162"}]) as serialize:
            exit_code = main(
                [
                    "--config",
                    str(config_file),
                    "--collect",
                    "qa-sessions",
                    "--start",
                    "2026-03-01",
                    "--end",
                    "2026-03-31",
                ]
            )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] is None
    assert payload["records"] == [{"remote_id": "13162"}]
    serialize.assert_called_once()


def test_cli_collects_qa_candidates(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "default-user"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    candidate = CandidateEntry(
        entry_type="linac_mqc",
        group_key="2026-03-06_LAx_linac_monthly",
        date="2026-03-06",
        title="LAx MQC",
    )

    with patch("radlog.cli.collect_qa_sessions", return_value=[{"remote_id": "13162"}]):
        with patch("radlog.cli.collect_service_events", return_value=[]):
            with patch("radlog.cli.serialize_source_records", return_value=[{"remote_id": "13162"}]):
                with patch("radlog.cli.group_source_records", return_value=[candidate]):
                    with patch("radlog.cli.load_callable", return_value=lambda candidate: "rendered org") as load:
                        exit_code = main(
                            [
                                "--config",
                                str(config_file),
                                "--collect",
                                "qa-candidates",
                                "--start",
                                "2026-03-01",
                                "--end",
                                "2026-03-31",
                            ]
                        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["server"] is None
    assert payload["records"] == [{"remote_id": "13162"}]
    assert payload["candidates"][0]["group_key"] == "2026-03-06_LAx_linac_monthly"
    assert payload["candidates"][0]["rendered_org"] == "rendered org"
    load.assert_called_once_with(
        "radlog.renderers.logbook_org:render_candidate",
        search_paths=[],
    )


def test_cli_collects_service_events_into_candidates(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "default-user"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")
    candidate = CandidateEntry(
        entry_type="abc_ad_hoc",
        group_key="2026-04-14_ABC_abc_ad_hoc",
        date="2026-04-14",
        title="ABC Ad hoc QA",
    )

    with patch("radlog.cli.collect_qa_sessions", return_value=[]):
        with patch("radlog.cli.collect_service_events", return_value=[{"remote_id": "324", "source_type": "service_event"}]):
            with patch(
                "radlog.cli.serialize_source_records",
                return_value=[{"remote_id": "324", "source_type": "service_event"}],
            ):
                with patch("radlog.cli.group_source_records", return_value=[candidate]):
                    with patch("radlog.cli.load_callable", return_value=lambda candidate: "rendered service org"):
                        exit_code = main(
                            [
                                "--config",
                                str(config_file),
                                "--collect",
                                "qa-candidates",
                                "--start",
                                "2026-04-01",
                                "--end",
                                "2026-04-20",
                            ]
                        )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["records"] == [{"remote_id": "324", "source_type": "service_event"}]
    assert payload["candidates"][0]["group_key"] == "2026-04-14_ABC_abc_ad_hoc"
    assert payload["candidates"][0]["rendered_org"] == "rendered service org"


def test_cli_rejects_invalid_param(capsys, tmp_path, monkeypatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    exit_code = main(["--config", str(config_file), "--param", "badparam"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "expected KEY=VALUE" in captured.err


def _issue(
    issue_type: str,
    test_label: str,
    comment: str | None = None,
    *,
    equipment_name: str = "LINAC-A - SiteName",
    equipment_group: str = "LINAC-A",
) -> QaIssue:
    return QaIssue(
        session_id="101",
        session_url=f"{TEST_BASE_URL}/{TEST_CUSTOMER_ID}/qa/session/details/101/",
        performed_at="2026-07-20T10:00:00+10:00",
        equipment_name=equipment_name,
        equipment_group=equipment_group,
        collection_name="Generic Monthly QA",
        test_label=test_label,
        issue_type=issue_type,
        severity=issue_type,
        value=4.2,
        pass_fail=issue_type,
        comment=comment,
    )

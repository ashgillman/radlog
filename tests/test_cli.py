from __future__ import annotations

import json
from unittest.mock import patch

from radlog.cli import main
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

    with patch("radlog.cli.collect_qa_sessions", return_value=[{"remote_id": "13162"}]):
        with patch("radlog.cli.collect_service_events", return_value=[]):
            with patch("radlog.cli.serialize_source_records", return_value=[{"remote_id": "13162"}]):
                with patch("radlog.cli.group_source_records", return_value=[{"group_key": "2026-03-06_LA7_linac_monthly"}]):
                    with patch(
                        "radlog.cli.serialize_candidate_entries",
                        return_value=[{"group_key": "2026-03-06_LA7_linac_monthly"}],
                    ):
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
    assert payload["candidates"] == [{"group_key": "2026-03-06_LA7_linac_monthly"}]


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

    with patch("radlog.cli.collect_qa_sessions", return_value=[]):
        with patch("radlog.cli.collect_service_events", return_value=[{"remote_id": "324", "source_type": "service_event"}]):
            with patch(
                "radlog.cli.serialize_source_records",
                return_value=[{"remote_id": "324", "source_type": "service_event"}],
            ):
                with patch(
                    "radlog.cli.group_source_records",
                    return_value=[{"group_key": "2026-04-14_ABC_abc_ad_hoc"}],
                ):
                    with patch(
                        "radlog.cli.serialize_candidate_entries",
                        return_value=[{"group_key": "2026-04-14_ABC_abc_ad_hoc"}],
                    ):
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
    assert payload["candidates"] == [{"group_key": "2026-04-14_ABC_abc_ad_hoc"}]


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

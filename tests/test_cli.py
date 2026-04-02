from __future__ import annotations

import json

from radlog.cli import main


def test_cli_emits_json_payload(capsys, tmp_path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "https://radmachine.radformation.com"
customer_id = "tcc"
username = "default-user"
""".strip()
    )

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
    assert payload["candidates"] == []


def test_cli_reports_missing_config(capsys) -> None:
    exit_code = main(["--config", "does-not-exist.toml"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "Config file not found" in captured.err

from __future__ import annotations

from pathlib import Path

from radlog.config import load_config


def test_load_config_reads_example(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "https://radmachine.radformation.com"
customer_id = "tcc"
username = "tester"
token_env = "RADMACHINE_TOKEN"

[logbook]
default_file = "~/org/logbook.org"
default_heading = "TCC Logbook"
timezone = "Australia/Brisbane"

[grouping]
merge_same_day_same_unit = true

[render]
include_durations = true
include_flagged_items = false
""".strip()
    )

    config = load_config(config_file)

    assert config.radmachine.base_url == "https://radmachine.radformation.com"
    assert config.radmachine.customer_id == "tcc"
    assert config.radmachine.username == "tester"
    assert config.logbook.default_file == "~/org/logbook.org"
    assert config.grouping.merge_same_day_same_unit is True
    assert config.render.include_flagged_items is False

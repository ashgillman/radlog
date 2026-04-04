from __future__ import annotations

import os
from pathlib import Path

import pytest

from radlog.config import ConfigError, get_token, load_config, validate_radmachine_config
from tests.support import TEST_BASE_URL, TEST_CUSTOMER_ID


def test_load_config_reads_example(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
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
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)

    assert config.radmachine.base_url == TEST_BASE_URL
    assert config.radmachine.customer_id == TEST_CUSTOMER_ID
    assert config.radmachine.username == "tester"
    assert config.logbook.default_file == "~/org/logbook.org"
    assert config.grouping.merge_same_day_same_unit is True
    assert config.render.include_flagged_items is False


def test_get_token_reads_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)
    monkeypatch.setenv("RADMACHINE_TOKEN", "secret-token")

    assert get_token(config) == "secret-token"


def test_get_token_requires_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)
    monkeypatch.delenv("RADMACHINE_TOKEN", raising=False)

    with pytest.raises(ConfigError):
        get_token(config)


def test_validate_radmachine_config_requires_base_url_and_customer_id(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[radmachine]\n")
    config = load_config(config_file)

    with pytest.raises(ConfigError):
        validate_radmachine_config(config)

from __future__ import annotations

import os
from pathlib import Path

import pytest

from radlog.config import (
    ConfigError,
    default_cache_dir,
    default_config_path,
    get_token,
    load_config,
    resolve_config_path,
    user_cache_dir,
    user_config_dir,
    validate_radmachine_config,
)
from radlog.extensions import load_callable
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
rules = "custom_rules:RULES"

[render]
include_durations = true
include_flagged_items = false
logbook_org_renderer = "custom_renderer:render"

[extensions]
paths = ["~/radlog-extensions"]

[reports.weekly-comments]
type = "qa"
title = "Weekly QA Comments"
last = "week"
user = "tester"
filter_by_results = "comment"
where = ["commenter = tester"]
render = "html-serve"
group_by = "date"
[reports.weekly-comments.params]
ordering = "-work_completed"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)

    assert config.radmachine.base_url == TEST_BASE_URL
    assert config.radmachine.customer_id == TEST_CUSTOMER_ID
    assert config.radmachine.username == "tester"
    assert config.logbook.default_file == "~/org/logbook.org"
    assert config.grouping.merge_same_day_same_unit is True
    assert config.grouping.rules == "custom_rules:RULES"
    assert config.render.include_flagged_items is False
    assert config.render.logbook_org_renderer == "custom_renderer:render"
    assert config.extensions.paths == ["~/radlog-extensions"]
    assert config.reports["weekly-comments"].type == "qa"
    assert config.reports["weekly-comments"].title == "Weekly QA Comments"
    assert config.reports["weekly-comments"].last == "week"
    assert config.reports["weekly-comments"].user == "tester"
    assert config.reports["weekly-comments"].filter_by_results == "comment"
    assert config.reports["weekly-comments"].where == ["commenter = tester"]
    assert config.reports["weekly-comments"].render == "html-serve"
    assert config.reports["weekly-comments"].group_by == "date"
    assert config.reports["weekly-comments"].params == {"ordering": "-work_completed"}


def test_load_config_accepts_direct_token(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
username = "tester"
token = "secret-token"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)

    assert config.radmachine.base_url == TEST_BASE_URL
    assert config.radmachine.customer_id == TEST_CUSTOMER_ID
    assert config.radmachine.username == "tester"
    assert config.radmachine.token == "secret-token"


def test_default_config_and_cache_paths_use_xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache-home"))

    assert user_config_dir() == tmp_path / "config-home" / "radlog"
    assert default_config_path() == tmp_path / "config-home" / "radlog" / "config.toml"
    assert user_cache_dir() == tmp_path / "cache-home" / "radlog"
    assert default_cache_dir() == tmp_path / "cache-home" / "radlog"


def test_default_config_and_cache_paths_use_windows_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr("radlog.config.sys.platform", "win32")

    assert user_config_dir() == tmp_path / "AppData" / "Roaming" / "radlog"
    assert user_cache_dir() == tmp_path / "AppData" / "Local" / "radlog" / "cache"


def test_resolve_config_path_prefers_explicit_then_env_then_user_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = tmp_path / "explicit.toml"
    env_path = tmp_path / "env.toml"
    user_path = tmp_path / "config-home" / "radlog" / "config.toml"
    user_path.parent.mkdir(parents=True)
    user_path.write_text("[radmachine]\n")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("RADLOG_CONFIG", str(env_path))

    assert resolve_config_path(explicit) == explicit
    assert resolve_config_path(None) == env_path
    monkeypatch.delenv("RADLOG_CONFIG")
    assert resolve_config_path(None) == user_path


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


def test_get_token_prefers_direct_config_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token = "config-token"
token_env = "RADMACHINE_TOKEN"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)
    monkeypatch.setenv("RADMACHINE_TOKEN", "env-token")

    assert get_token(config) == "config-token"


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


def test_get_token_reports_token_value_in_token_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        """
[radmachine]
base_url = "{base_url}"
customer_id = "{customer_id}"
token_env = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
""".strip().format(base_url=TEST_BASE_URL, customer_id=TEST_CUSTOMER_ID)
    )

    config = load_config(config_file)
    monkeypatch.delenv("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", raising=False)

    with pytest.raises(ConfigError, match="Use radmachine.token for direct tokens"):
        get_token(config)


def test_validate_radmachine_config_requires_base_url_and_customer_id(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[radmachine]\n")
    config = load_config(config_file)

    with pytest.raises(ConfigError):
        validate_radmachine_config(config)


def test_load_callable_imports_from_extension_path(tmp_path: Path) -> None:
    extension_file = tmp_path / "custom_renderer.py"
    extension_file.write_text(
        """
def render(candidate):
    return candidate.title
""".strip()
    )

    renderer = load_callable("custom_renderer:render", search_paths=[str(tmp_path)])

    assert renderer(type("Candidate", (), {"title": "Rendered"})()) == "Rendered"


def test_load_callable_rejects_invalid_spec() -> None:
    with pytest.raises(ConfigError):
        load_callable("custom_renderer.render")

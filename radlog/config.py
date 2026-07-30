"""Configuration loading for the RadMachine importer."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(slots=True)
class RadMachineConfig:
    base_url: str = ""
    customer_id: str = ""
    username: str | None = None
    token: str | None = None
    token_env: str = "RADMACHINE_TOKEN"


@dataclass(slots=True)
class LogbookConfig:
    default_file: str | None = None
    default_heading: str | None = None
    timezone: str = "Australia/Brisbane"


@dataclass(slots=True)
class GroupingConfig:
    merge_same_day_same_unit: bool = True
    rules: str = "radlog.site_rules:DEFAULT_RULES"


@dataclass(slots=True)
class RenderConfig:
    include_durations: bool = True
    include_flagged_items: bool = True
    logbook_org_renderer: str = "radlog.renderers.logbook_org:render_candidate"


@dataclass(slots=True)
class ExtensionsConfig:
    paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReportPresetConfig:
    type: str = "qa"
    title: str | None = None
    start: str | None = None
    end: str | None = None
    last: str | None = None
    user: str | None = None
    filter_by_results: str | None = None
    where: list[str] = field(default_factory=list)
    render: str | None = None
    group_by: str | None = None
    params: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Config:
    radmachine: RadMachineConfig
    logbook: LogbookConfig
    grouping: GroupingConfig
    render: RenderConfig
    extensions: ExtensionsConfig
    reports: dict[str, ReportPresetConfig] = field(default_factory=dict)


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def default_config_path() -> Path:
    return user_config_dir() / "config.toml"


def default_cache_dir() -> Path:
    return user_cache_dir()


def user_config_dir() -> Path:
    override = os.environ.get("XDG_CONFIG_HOME")
    if override:
        return Path(override).expanduser() / "radlog"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "radlog"
    return Path.home() / ".config" / "radlog"


def user_cache_dir() -> Path:
    override = os.environ.get("XDG_CACHE_HOME")
    if override:
        return Path(override).expanduser() / "radlog"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "radlog" / "cache"
    return Path.home() / ".cache" / "radlog"


def resolve_config_path(path: str | Path | None) -> Path:
    if path:
        return Path(path).expanduser()

    env_path = os.environ.get("RADLOG_CONFIG")
    if env_path:
        return Path(env_path).expanduser()

    config_path = default_config_path()
    if config_path.exists():
        return config_path

    local_path = Path("config.toml")
    if local_path.exists():
        return local_path

    return config_path


def load_config(path: str | Path) -> Config:
    raw = _load_toml(path)
    radmachine = _radmachine_config(raw)
    return Config(
        radmachine=RadMachineConfig(**radmachine),
        logbook=LogbookConfig(**raw.get("logbook", {})),
        grouping=GroupingConfig(**raw.get("grouping", {})),
        render=RenderConfig(**raw.get("render", {})),
        extensions=ExtensionsConfig(**raw.get("extensions", {})),
        reports=_reports_config(raw),
    )


def _load_toml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} did not contain a TOML table")
    return data


def _radmachine_config(raw: dict[str, Any]) -> dict[str, Any]:
    if "radmachine" in raw:
        value = raw.get("radmachine", {})
        if not isinstance(value, dict):
            raise ConfigError("radmachine config must be a TOML table")
        return value

    flat_keys = {"base_url", "customer_id", "username", "token", "token_env"}
    return {key: raw[key] for key in flat_keys if key in raw}


def _reports_config(raw: dict[str, Any]) -> dict[str, ReportPresetConfig]:
    reports = raw.get("reports", {})
    if not isinstance(reports, dict):
        raise ConfigError("reports config must be a TOML table")

    presets: dict[str, ReportPresetConfig] = {}
    for name, value in reports.items():
        if not isinstance(value, dict):
            raise ConfigError(f"reports.{name} config must be a TOML table")
        preset = dict(value)
        if "where" in preset and isinstance(preset["where"], str):
            preset["where"] = [preset["where"]]
        if "params" in preset:
            params = preset["params"]
            if not isinstance(params, dict):
                raise ConfigError(f"reports.{name}.params must be a TOML table")
            preset["params"] = {str(key): str(param_value) for key, param_value in params.items()}
        presets[str(name)] = ReportPresetConfig(**preset)
    return presets


def get_token(config: Config) -> str:
    if config.radmachine.token:
        return config.radmachine.token

    token_env = config.radmachine.token_env
    if not token_env:
        raise ConfigError("radmachine.token_env must name the environment variable holding the API token")
    if _looks_like_token_literal(token_env):
        raise ConfigError(
            "radmachine.token_env appears to contain an API token value. "
            "Use radmachine.token for direct tokens, or set token_env to an environment variable name."
        )

    token = os.environ.get(token_env)
    if not token:
        raise ConfigError(
            f"Environment variable {token_env} is not set; export the RadMachine API token before running radlog"
        )
    return token


def _looks_like_token_literal(value: str) -> bool:
    return len(value) >= 32 and value.upper() != value


def validate_radmachine_config(config: Config) -> None:
    if not config.radmachine.base_url:
        raise ConfigError("radmachine.base_url is required")
    if not config.radmachine.customer_id:
        raise ConfigError("radmachine.customer_id is required")

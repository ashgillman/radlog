"""Configuration loading for the RadMachine importer."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
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
class Config:
    radmachine: RadMachineConfig
    logbook: LogbookConfig
    grouping: GroupingConfig
    render: RenderConfig
    extensions: ExtensionsConfig


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def load_config(path: str | Path) -> Config:
    raw = _load_toml(path)
    return Config(
        radmachine=RadMachineConfig(**raw.get("radmachine", {})),
        logbook=LogbookConfig(**raw.get("logbook", {})),
        grouping=GroupingConfig(**raw.get("grouping", {})),
        render=RenderConfig(**raw.get("render", {})),
        extensions=ExtensionsConfig(**raw.get("extensions", {})),
    )


def _load_toml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} did not contain a TOML table")
    return data


def get_token(config: Config) -> str:
    token_env = config.radmachine.token_env
    if not token_env:
        raise ConfigError("radmachine.token_env must name the environment variable holding the API token")

    token = os.environ.get(token_env)
    if not token:
        raise ConfigError(
            f"Environment variable {token_env} is not set; export the RadMachine API token before running radlog"
        )
    return token


def validate_radmachine_config(config: Config) -> None:
    if not config.radmachine.base_url:
        raise ConfigError("radmachine.base_url is required")
    if not config.radmachine.customer_id:
        raise ConfigError("radmachine.customer_id is required")

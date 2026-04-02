"""Configuration loading for the RadMachine importer."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(slots=True)
class RenderConfig:
    include_durations: bool = True
    include_flagged_items: bool = True


@dataclass(slots=True)
class Config:
    radmachine: RadMachineConfig
    logbook: LogbookConfig
    grouping: GroupingConfig
    render: RenderConfig


def load_config(path: str | Path) -> Config:
    raw = _load_toml(path)
    return Config(
        radmachine=RadMachineConfig(**raw.get("radmachine", {})),
        logbook=LogbookConfig(**raw.get("logbook", {})),
        grouping=GroupingConfig(**raw.get("grouping", {})),
        render=RenderConfig(**raw.get("render", {})),
    )


def _load_toml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {config_path} did not contain a TOML table")
    return data

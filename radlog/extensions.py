"""Load user-provided extension callables."""

from __future__ import annotations

from collections.abc import Callable
import importlib
import sys
from pathlib import Path
from typing import Any

from .config import ConfigError


def load_object(spec: str, *, search_paths: list[str] | None = None) -> Any:
    """Load an object named by MODULE:ATTRIBUTE."""
    module_name, sep, attribute_name = spec.partition(":")
    if not sep or not module_name or not attribute_name:
        raise ConfigError(f"Invalid extension spec {spec!r}; expected MODULE:ATTRIBUTE")

    for path in search_paths or []:
        expanded = str(Path(path).expanduser())
        if expanded not in sys.path:
            sys.path.insert(0, expanded)

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"Could not import extension module {module_name!r}") from exc

    try:
        loaded = getattr(module, attribute_name)
    except AttributeError as exc:
        raise ConfigError(f"Extension module {module_name!r} has no attribute {attribute_name!r}") from exc

    return loaded


def load_callable(spec: str, *, search_paths: list[str] | None = None) -> Callable[..., Any]:
    """Load a callable named by MODULE:ATTRIBUTE."""
    loaded = load_object(spec, search_paths=search_paths)
    if not callable(loaded):
        raise ConfigError(f"Extension {spec!r} is not callable")
    return loaded

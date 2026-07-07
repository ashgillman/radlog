"""Compatibility imports for the default Org logbook renderer."""

from __future__ import annotations

from .renderers.logbook_org import render_candidate, render_generic

__all__ = [
    "render_candidate",
    "render_generic",
]

"""Resolve app resource paths for source and frozen (PyInstaller) runs."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Project root in development, or the PyInstaller bundle root when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def ui_dir() -> Path:
    return app_root() / "ui"

"""Office and related types that need a user-made PDF before printing."""

from __future__ import annotations

import os

OFFICE_EXCEL = {".xls", ".xlsx", ".xlsm", ".xlsb", ".ods"}
OFFICE_WORD = {".doc", ".docx", ".docm", ".rtf", ".odt", ".html", ".htm"}
OFFICE_PPT = {".ppt", ".pptx", ".pptm", ".odp"}
CONVERTIBLE_EXTS = OFFICE_EXCEL | OFFICE_WORD | OFFICE_PPT | {".ps"}


def extension_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def is_convertible(path: str) -> bool:
    """True for Office/HTML/ODF/PS — convert to PDF in their own app first."""
    return extension_of(path) in CONVERTIBLE_EXTS

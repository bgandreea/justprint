"""Paper sizes for layout and for the Windows print job.

Portrait dimensions. Windows ids are DMPAPER_* values. Sizes without an id
are sent as a custom form with the width and length in tenths of a millimeter.
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4
DMPAPER_USER = 256


@dataclass(frozen=True)
class Paper:
    key: str
    name: str
    label: str
    group: str
    width_mm: float
    height_mm: float
    win_id: int | None = None
    form: str = ""


def _inches(width: float, height: float) -> tuple[float, float]:
    return round(width * MM_PER_INCH, 1), round(height * MM_PER_INCH, 1)


_LETTER = _inches(8.5, 11)
_LEGAL = _inches(8.5, 14)
_TABLOID = _inches(11, 17)
_PHOTO = {
    "4x6": _inches(4, 6),
    "5x7": _inches(5, 7),
    "8x10": _inches(8, 10),
    "11x14": _inches(11, 14),
    "16x20": _inches(16, 20),
    "20x30": _inches(20, 30),
    "24x36": _inches(24, 36),
}

PAPER_LIST: tuple[Paper, ...] = (
    Paper("a0", "A0", "A0 (841 × 1189 mm)", "ISO", 841, 1189, None, "A0"),
    Paper("a1", "A1", "A1 (594 × 841 mm)", "ISO", 594, 841, None, "A1"),
    Paper("a2", "A2", "A2 (420 × 594 mm)", "ISO", 420, 594, 66, "A2"),
    Paper("a3", "A3", "A3 (297 × 420 mm)", "ISO", 297, 420, 8, "A3"),
    Paper("a4", "A4", "A4 (210 × 297 mm)", "ISO", 210, 297, 9, "A4"),
    Paper("a5", "A5", "A5 (148 × 210 mm)", "ISO", 148, 210, 11, "A5"),
    Paper("a6", "A6", "A6 (105 × 148 mm)", "ISO", 105, 148, 70, "A6"),
    Paper("a7", "A7", "A7 (74 × 105 mm)", "ISO", 74, 105, None, "A7"),
    Paper("letter", "Letter", "Letter (8.5 × 11 in)", "North America", _LETTER[0], _LETTER[1], 1, "Letter"),
    Paper("legal", "Legal", "Legal (8.5 × 14 in)", "North America", _LEGAL[0], _LEGAL[1], 5, "Legal"),
    Paper("tabloid", "Tabloid", "Tabloid (11 × 17 in)", "North America", _TABLOID[0], _TABLOID[1], 3, "Tabloid"),
    Paper("photo4x6", "4 × 6 in", "4 × 6 in", "Photo", _PHOTO["4x6"][0], _PHOTO["4x6"][1], None, "4x6"),
    Paper("photo5x7", "5 × 7 in", "5 × 7 in", "Photo", _PHOTO["5x7"][0], _PHOTO["5x7"][1], None, "5x7"),
    Paper("photo8x10", "8 × 10 in", "8 × 10 in", "Photo", _PHOTO["8x10"][0], _PHOTO["8x10"][1], None, "8x10"),
    Paper("photo11x14", "11 × 14 in", "11 × 14 in", "Photo", _PHOTO["11x14"][0], _PHOTO["11x14"][1], None, "11x14"),
    Paper("photo16x20", "16 × 20 in", "16 × 20 in", "Photo", _PHOTO["16x20"][0], _PHOTO["16x20"][1], None, "16x20"),
    Paper("photo20x30", "20 × 30 in", "20 × 30 in", "Photo", _PHOTO["20x30"][0], _PHOTO["20x30"][1], None, "20x30"),
    Paper("photo24x36", "24 × 36 in", "24 × 36 in", "Photo", _PHOTO["24x36"][0], _PHOTO["24x36"][1], None, "24x36"),
)

BY_KEY = {paper.key: paper for paper in PAPER_LIST}
PAPER_KEYS = {"default", *BY_KEY}
# DMPAPER_11X17 is the same sheet as Tabloid.
WIN_TO_KEY = {paper.win_id: paper.key for paper in PAPER_LIST if paper.win_id is not None}
WIN_TO_KEY[17] = "tabloid"


def paper_name(key: str) -> str:
    if key == "default":
        return "Printer default"
    spec = BY_KEY.get(key)
    return spec.name if spec else "Letter"


def paper_inches(key: str) -> tuple[float, float]:
    spec = BY_KEY.get(key) or BY_KEY["letter"]
    return spec.width_mm / MM_PER_INCH, spec.height_mm / MM_PER_INCH


def devmode_paper(key: str) -> dict | None:
    """Fields to put on a Windows DEVMODE. None leaves the printer's paper alone."""
    spec = BY_KEY.get(key)
    if spec is None:
        return None
    if spec.win_id is not None:
        return {"size": spec.win_id, "form": spec.form, "custom": False}
    return {
        "size": DMPAPER_USER,
        "form": spec.form,
        "custom": True,
        "width": int(round(spec.width_mm * 10)),
        "length": int(round(spec.height_mm * 10)),
    }


def match_win_paper(paper_id: int, width_tenth_mm: int = 0, length_tenth_mm: int = 0) -> str | None:
    """Map a printer's current form back to one of our sizes."""
    key = WIN_TO_KEY.get(int(paper_id or 0))
    if key:
        return key
    if not width_tenth_mm or not length_tenth_mm:
        return None
    width, height = sorted((width_tenth_mm / 10, length_tenth_mm / 10))
    best_key = None
    best_delta = 1.6
    for spec in PAPER_LIST:
        sw, sh = sorted((spec.width_mm, spec.height_mm))
        delta = abs(sw - width) + abs(sh - height)
        if delta < best_delta:
            best_key = spec.key
            best_delta = delta
    return best_key

"""Page ranges and sheet counting."""

from __future__ import annotations

import re


def parse_range(spec: str, page_count: int) -> list[int]:
    """Return 1-based page numbers for a range such as ``all`` or ``1-3,5``.

    ``1-`` means from that page through the end. ``-3`` means the first pages.
    """
    text = (spec or "").strip().lower()
    if text in {"", "all", "*"}:
        return list(range(1, page_count + 1))
    if page_count <= 0:
        raise ValueError("This file has no pages")

    pages: list[int] = []
    seen: set[int] = set()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise ValueError("Enter a page range, or all")

    for part in parts:
        span = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if span:
            start_text, end_text = span.group(1), span.group(2)
            if not start_text and not end_text:
                raise ValueError(f"Invalid range '{part}'")
            start = int(start_text) if start_text else 1
            end = int(end_text) if end_text else page_count
            if start < 1 or end < 1 or start > end:
                raise ValueError(f"Invalid range '{part}'")
            if end > page_count:
                raise ValueError(f"Page {end} is past the end ({page_count} pages)")
            numbers = range(start, end + 1)
        elif re.fullmatch(r"\d+", part):
            number = int(part)
            if number < 1 or number > page_count:
                raise ValueError(f"Page {number} is past the end ({page_count} pages)")
            numbers = (number,)
        else:
            raise ValueError(f"Invalid range '{part}'")
        for number in numbers:
            if number not in seen:
                seen.add(number)
                pages.append(number)
    if not pages:
        raise ValueError("Enter a page range, or all")
    return pages


def physical_sheets(page_count: int, copies: int, duplex: str) -> int:
    """Physical sheets that will leave the printer."""
    if page_count <= 0 or copies <= 0:
        return 0
    per_copy = page_count if duplex == "simplex" else (page_count + 1) // 2
    return per_copy * copies


def iter_groups(pages: list[int], copies: int, *, duplex: str, collate: bool):
    """Groups of pages, where each group is one spool document.

    Duplex jobs are always collated so the back of one copy cannot pick up
    the first page of the next copy.
    """
    if copies < 1 or not pages:
        return
    if duplex == "simplex" and not collate:
        for page in pages:
            for _copy in range(copies):
                yield [page]
        return
    for _copy in range(copies):
        yield list(pages)


class SheetProgress:
    """Counts physical sheets the same way the print loop emits pages."""

    def __init__(self, duplex: bool):
        self.duplex = duplex
        self.physical = 0
        self._front = False

    def side_sent(self) -> None:
        if not self.duplex:
            self.physical += 1
            return
        if not self._front:
            self._front = True
            return
        self._front = False
        self.physical += 1

    def end_copy(self) -> None:
        if self._front:
            self._front = False
            self.physical += 1


def simulate_sheets(pages: list[int], copies: int, duplex: str, collate: bool) -> int:
    progress = SheetProgress(duplex != "simplex")
    for group in iter_groups(pages, copies, duplex=duplex, collate=collate):
        for _page in group:
            progress.side_sent()
        progress.end_copy()
    return progress.physical


def filter_pages(pages: list[int], settings: dict) -> list[int]:
    """Apply odd/even and reverse-order options."""
    parity = str(settings.get("parity") or "all").lower()
    if parity == "odd":
        pages = [page for page in pages if page % 2 == 1]
    elif parity == "even":
        pages = [page for page in pages if page % 2 == 0]
    if settings.get("reverse_order"):
        pages = list(reversed(pages))
    return pages


def booklet_order(pages: list[int], binding: str = "left") -> list[int]:
    """Reorder pages for booklet imposition (padded to a multiple of 4)."""
    if not pages:
        return []
    padded = list(pages)
    while len(padded) % 4:
        padded.append(0)  # 0 = blank filler
    sheets = len(padded) // 4
    ordered: list[int] = []
    for sheet in range(sheets):
        # Signature: back-left, front-right, front-left, back-right for left binding.
        a = padded[-(sheet * 2 + 1)]
        b = padded[sheet * 2]
        c = padded[sheet * 2 + 1]
        d = padded[-(sheet * 2 + 2)]
        if str(binding).lower() == "right":
            ordered.extend([b, a, d, c])
        else:
            ordered.extend([a, b, c, d])
    return ordered


def nup_grid(n_up: int) -> tuple[int, int]:
    """Return (cols, rows) for an n-up sheet."""
    grids = {
        1: (1, 1),
        2: (2, 1),
        4: (2, 2),
        6: (3, 2),
        9: (3, 3),
        16: (4, 4),
    }
    return grids.get(int(n_up or 1), (1, 1))


def chunk_pages(pages: list[int], size: int) -> list[list[int]]:
    if size <= 1:
        return [[page] for page in pages]
    chunks: list[list[int]] = []
    for index in range(0, len(pages), size):
        chunk = pages[index : index + size]
        while len(chunk) < size:
            chunk.append(0)
        chunks.append(chunk)
    return chunks


def sheet_page_groups(pages: list[int], settings: dict) -> list[list[int]]:
    """Group logical pages into physical sheet faces (n-up or booklet)."""
    if settings.get("booklet"):
        ordered = booklet_order(pages, settings.get("booklet_binding") or "left")
        return chunk_pages(ordered, 2)
    n_up = int(settings.get("n_up") or 1)
    if n_up <= 1:
        return [[page] for page in pages]
    return chunk_pages(pages, n_up)


def physical_sheets_for_settings(page_count: int, copies: int, settings: dict) -> int:
    """Estimate sheets accounting for n-up / booklet."""
    if page_count <= 0 or copies <= 0:
        return 0
    pages = list(range(1, page_count + 1))
    pages = filter_pages(pages, settings)
    groups = sheet_page_groups(pages, settings)
    sheet_faces = max(1, len(groups)) if pages else 0
    duplex = settings.get("duplex", "simplex")
    if duplex == "simplex":
        return sheet_faces * copies
    return ((sheet_faces + 1) // 2) * copies

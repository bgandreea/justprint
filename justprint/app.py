"""Document queue, settings, and the print job."""

from __future__ import annotations

import copy
import io
import json
import os
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from justprint.pages import (
    SheetProgress,
    filter_pages,
    iter_groups,
    parse_range,
    physical_sheets_for_settings,
    sheet_page_groups,
)
from justprint.officeconvert import is_convertible
from justprint.papers import PAPER_KEYS
from justprint.render import (
    classify,
    compose_nup,
    decorate_page,
    inspect_pages,
    is_allowed,
    is_blank_page,
    labeled_separator,
    open_source,
    orientation_for,
    prepare,
    render_test_page,
    RenderError,
)
from justprint.options import (
    PAGE_OPTION_DEFAULTS,
    apply_option_setting,
    merge_option_defaults,
    preset_option_block,
    public_option_settings,
)
from justprint.spool import (
    HAS_SPOOL,
    SPOOL_ERROR,
    SpoolError,
    default_printer,
    list_printers,
    make_sink,
    printer_defaults,
    printer_status,
)

PAPERS = PAPER_KEYS
PAPER_TRAYS = {"default", "auto", "upper", "lower", "manual", "cassette"}
ORIENTATIONS = {"auto", "portrait", "landscape"}
COLORS = {"color", "grayscale"}
DUPLEXES = {"simplex", "long", "short"}
PRINTED_ACTIONS = {"none", "move", "copy"}
SETTING_ALIASES = {
    "defaultCopies": "default_copies",
    "practiceRun": "practice_run",
    "singleJob": "single_job",
    "pauseBeforeDocument": "pause_before_document",
    "waitForEmptyQueue": "wait_for_empty_queue",
    "sheetsPerMinute": "sheets_per_minute",
    "printerSheetsPerMinute": "sheets_per_minute",
    "removePrintedAfter": "remove_printed_after",
    "removePrinted": "remove_printed_after",
    "showSummary": "show_summary",
    "printedAction": "printed_action",
    "printedFolder": "printed_folder",
    "adoptPrinterDefaults": "adopt_printer_defaults",
    "windowWidth": "window_width",
    "windowHeight": "window_height",
    "paperTray": "paper_tray",
    "batchRepeat": "batch_repeat",
    "pageRange": "page_range",
    "range": "page_range",
    "documentOnFront": "document_on_front",
    "documentOnFrontSide": "document_on_front",
    "customPaperWidth": "custom_paper_width",
    "customPaperHeight": "custom_paper_height",
    "copies": "default_copies",
    "monochrome": "monochrome",
}

DEFAULT_SETTINGS = {
    "printer": "",
    "paper": "default",
    "paper_tray": "default",
    "orientation": "auto",
    "color": "color",
    "duplex": "simplex",
    "default_copies": 1,
    "collate": True,
    "batch_repeat": 1,
    "page_range": "",
    "document_on_front": True,
    "custom_paper_width": 0,
    "custom_paper_height": 0,
    "subfolders": True,
    "types": {"pdf": True, "images": True, "text": True},
    "practice_run": False,
    "single_job": False,
    "pause_before_document": 0,
    "wait_for_empty_queue": True,
    "sheets_per_minute": 0,
    "remove_printed_after": False,
    "show_summary": True,
    "printed_action": "none",
    "printed_folder": "",
    "adopt_printer_defaults": True,
    "window_width": 1540,
    "window_height": 860,
    **copy.deepcopy(PAGE_OPTION_DEFAULTS),
}

_OFFICE_GLOBS = (
    "*.xls *.xlsx *.xlsm *.xlsb *.ods "
    "*.doc *.docx *.docm *.rtf *.odt *.html *.htm "
    "*.ppt *.pptx *.pptm *.odp *.ps"
)
_OFFICE_WEB = (
    "*.xls;*.xlsx;*.xlsm;*.xlsb;*.ods;"
    "*.doc;*.docx;*.docm;*.rtf;*.odt;*.html;*.htm;"
    "*.ppt;*.pptx;*.pptm;*.odp;*.ps"
)
FILETYPES = (
    (
        "Supported documents",
        f"*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.txt *.log *.csv {_OFFICE_GLOBS}",
    ),
    ("PDF", "*.pdf"),
    ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp"),
    ("Text", "*.txt *.log *.csv"),
    ("Office and documents", _OFFICE_GLOBS),
    ("All files", "*.*"),
)
WEBVIEW_TYPES = (
    (
        "Supported (*.pdf;*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp;*.txt;*.log;*.csv;"
        f"{_OFFICE_WEB})"
    ),
    "PDF (*.pdf)",
    "Images (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp)",
    "Text (*.txt;*.log;*.csv)",
    f"Office and documents ({_OFFICE_WEB})",
    "All files (*.*)",
)


class StopPrint(Exception):
    """The user pressed Stop."""


@dataclass
class Document:
    id: str
    path: str
    name: str
    kind: str
    type_label: str
    pages: int | None
    size: int
    modified: float
    copies: int | None
    range_spec: str
    selected: bool
    status: str
    error: str | None
    inspecting: bool


@dataclass
class WorkItem:
    id: str
    path: str
    name: str
    copies: int
    range_spec: str


@dataclass
class Job:
    running: bool = False
    phase: str = "idle"
    message: str = ""
    file_index: int = 0
    file_total: int = 0
    sheets_printed: int = 0
    sheets_total: int = 0
    current_id: str | None = None
    current_name: str = ""
    current_page: int = 0
    current_pages: int = 0
    device_pages_printed: int = 0
    device_pages_total: int = 0


def _drop_relative(name: str) -> Path:
    raw = str(name or "").replace("\\", "/").strip()
    parts: list[str] = []
    for part in raw.split("/"):
        part = part.strip().rstrip(".")
        if not part or part in {".", ".."}:
            continue
        if _ILLEGAL_NAME.search(part) or part.upper() in _RESERVED_NAMES or _DEVICE_NAME.fullmatch(part.upper()):
            raise ValueError("That file name is not allowed")
        parts.append(part[:180])
    if not parts or len(parts) > 24:
        raise ValueError("That file name is not allowed")
    return Path(*parts)


_ILLEGAL_NAME = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"}
_DEVICE_NAME = re.compile(r"(COM|LPT)[1-9]")


def state_path() -> Path:
    override = os.environ.get("JUSTPRINT_HOME")
    if override:
        root = Path(override)
    else:
        appdata = Path(os.environ.get("APPDATA") or Path.home())
        root = appdata / "JustPrint"
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.json"


def apply_settings(current: dict, patch: dict) -> dict:
    updated = copy.deepcopy(current)
    for raw_key, value in patch.items():
        key = SETTING_ALIASES.get(raw_key, raw_key)
        if key == "printer":
            name = str(value or "").strip()
            if len(name) > 220:
                raise ValueError("That printer name is too long")
            updated["printer"] = name
        elif key == "paper":
            paper = str(value or "").strip().lower()
            if paper not in PAPERS:
                raise ValueError("Choose a paper size")
            updated["paper"] = paper
        elif key == "paper_tray":
            tray = str(value or "default").strip().lower()
            if tray not in PAPER_TRAYS:
                raise ValueError("Choose a paper tray")
            updated["paper_tray"] = tray
        elif key == "orientation":
            orientation = str(value or "").strip().lower()
            if orientation not in ORIENTATIONS:
                raise ValueError("Choose an orientation")
            updated["orientation"] = orientation
        elif key == "color":
            if value not in COLORS:
                raise ValueError("Choose color or black and white")
            updated["color"] = value
        elif key == "monochrome":
            updated["color"] = "grayscale" if bool(value) else "color"
        elif key == "duplex":
            duplex = _normalize_duplex(value)
            if duplex not in DUPLEXES:
                raise ValueError("Choose which sides to print")
            updated["duplex"] = duplex
        elif key == "default_copies":
            copies = int(value)
            if not 1 <= copies <= 99:
                raise ValueError("Default copies must be from 1 to 99")
            updated["default_copies"] = copies
        elif key == "batch_repeat":
            repeats = int(value)
            if not 1 <= repeats <= 99:
                raise ValueError("Repeat count must be from 1 to 99")
            updated["batch_repeat"] = repeats
        elif key == "page_range":
            spec = str(value or "").strip()
            if len(spec) > 80:
                raise ValueError("That page range is too long")
            if spec:
                _validate_range_syntax(spec)
            updated["page_range"] = spec
        elif key in {
            "collate",
            "subfolders",
            "practice_run",
            "single_job",
            "wait_for_empty_queue",
            "remove_printed_after",
            "show_summary",
            "adopt_printer_defaults",
            "document_on_front",
        }:
            updated[key] = bool(value)
        elif key == "pause_before_document":
            seconds = int(value)
            if not 0 <= seconds <= 600:
                raise ValueError("Pause between files must be from 0 to 600 seconds")
            updated["pause_before_document"] = seconds
        elif key == "sheets_per_minute":
            speed = int(value)
            if not 0 <= speed <= 300:
                raise ValueError("Sheets per minute must be from 0 to 300")
            updated["sheets_per_minute"] = speed
        elif key in {"custom_paper_width", "custom_paper_height"}:
            size = float(value)
            if not 0 <= size <= 2000:
                raise ValueError("Custom paper size must be from 0 to 2000 mm")
            updated[key] = int(size) if size == int(size) else round(size, 1)
        elif key == "printed_action":
            action = str(value or "none").strip().lower()
            if action not in PRINTED_ACTIONS:
                raise ValueError("Choose none, move, or copy for printed files")
            updated["printed_action"] = action
        elif key == "printed_folder":
            folder = str(value or "").strip()
            if len(folder) > 400:
                raise ValueError("That folder path is too long")
            updated["printed_folder"] = folder
        elif key in {"window_width", "window_height"}:
            size = int(value)
            if not 640 <= size <= 4000:
                raise ValueError("Window size is out of range")
            updated[key] = size
        elif key == "types":
            types = dict(updated["types"])
            incoming = value or {}
            if not isinstance(incoming, dict):
                raise ValueError("File types were not understood")
            for name in ("pdf", "images", "text"):
                if name in incoming:
                    types[name] = bool(incoming[name])
            if not any(types.values()):
                raise ValueError("Leave at least one file type turned on")
            updated["types"] = types
        elif apply_option_setting(updated, key, value):
            pass
    merge_option_defaults(updated)
    return updated


def _normalize_duplex(value) -> str:
    text = str(value or "").strip().lower()
    return {
        "none": "simplex",
        "simplex": "simplex",
        "one-sided": "simplex",
        "one sided": "simplex",
        "long": "long",
        "vertical": "long",
        "short": "short",
        "horizontal": "short",
    }.get(text, text)


def _validate_range_syntax(spec: str) -> None:
    """Reject obviously bad global ranges before pages are known."""
    text = spec.strip().lower()
    if text in {"", "all", "*"}:
        return
    for part in (piece.strip() for piece in text.split(",") if piece.strip()):
        if re.fullmatch(r"\d*", part):
            continue
        if re.fullmatch(r"\d*\s*-\s*\d*", part):
            continue
        raise ValueError(f"Invalid range '{part}'")


class App:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.documents: list[Document] = []
        self.job = Job()
        self.notice = ""
        self.notice_until = 0.0
        self.drop_tick = 0
        self.pending_warning: str | None = None
        self.last_summary: dict | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.window = None
        self._list_discarded = False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="justprint-read")
        self.preview_cache: dict[tuple, bytes] = {}
        self.preview_lock = threading.Lock()
        self._dialogs = DialogBridge()
        self._printer_names: list[str] = []
        self._printer_names_at = 0.0
        self._status_cache: dict[str, tuple[float, dict]] = {}
        raw_delay = os.environ.get("JUSTPRINT_PRACTICE_DELAY", "")
        try:
            self.practice_delay = float(raw_delay) if raw_delay else 0.0
        except ValueError:
            self.practice_delay = 0.0
        self._load()

    def pick_files(self) -> dict:
        paths = self._choose("files")
        if not paths:
            return {"cancelled": True}
        return self.add_paths(paths)

    def pick_folder(self) -> dict:
        paths = self._choose("folder")
        if not paths:
            return {"cancelled": True}
        return self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> dict:
        """Queue PDF/image/text. Office and similar types are skipped with a warning."""
        self._require_idle()
        settings = self._settings_copy()
        roots = [os.path.abspath(os.path.expanduser(str(raw))) for raw in paths]
        natives, convertibles, missing, unsupported = _scan_add_paths(roots, settings)

        added = 0
        duplicate = 0
        new_ids: list[str] = []
        with self.lock:
            existing = {os.path.normcase(doc.path) for doc in self.documents}
            for path in natives:
                result = self._queue_locked(path, existing)
                if result == "duplicate":
                    duplicate += 1
                elif result == "unsupported":
                    unsupported += 1
                else:
                    added += 1
                    new_ids.append(result)
            self._write_state()
        for doc_id in new_ids:
            self.executor.submit(self._inspect, doc_id)

        skipped_names = [os.path.basename(path) for path in convertibles[:8]]
        message = _added_message(
            added,
            duplicate,
            unsupported,
            missing,
            needs_pdf=len(convertibles),
            needs_pdf_names=skipped_names,
        )
        warning = None
        if convertibles:
            listed = ", ".join(skipped_names)
            extra = len(convertibles) - len(skipped_names)
            if extra > 0:
                listed = f"{listed}, and {extra} more" if listed else f"{extra} more"
            if len(convertibles) == 1:
                warning = (
                    f"{listed or 'This file'} cannot be printed here. "
                    "Convert it to PDF in Excel/Word (or its own app) with the page size you want, then add that PDF."
                )
            else:
                warning = (
                    f"{len(convertibles)} files cannot be printed here ({listed}). "
                    "Convert them to PDF in their own apps with the page size you want, then add those PDFs."
                )
        with self.lock:
            self.pending_warning = warning
        self._set_notice(message, seconds=20.0 if warning else 8.0)
        return {
            "added": added,
            "duplicate": duplicate,
            "unsupported": unsupported,
            "missing": missing,
            "needsPdf": len(convertibles),
            "warning": warning,
            "message": message,
        }

    def dismiss_warning(self) -> None:
        with self.lock:
            self.pending_warning = None

    def store_drop(self, batch: str, name: str, data: bytes) -> str:
        """Save a browser drop, which has no real disk path, and return the copy's path."""
        if len(data) > 200_000_000:
            raise ValueError("That file is too large to drop here. Use Add files for files over 200 MB.")
        try:
            token = str(uuid.UUID(str(batch).strip()))
        except ValueError as exc:
            raise ValueError("That drop was not understood") from exc
        relative = _drop_relative(name)
        root = (state_path().parent / "dropped" / token).resolve()
        destination = (root / relative).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError("That file name is not allowed") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return str(destination)

    def note_drop(self) -> None:
        with self.lock:
            self.drop_tick += 1

    def update_document(self, payload: dict) -> None:
        self._require_idle()
        doc_id = str(payload.get("id") or "")
        with self.lock:
            doc = self._doc(doc_id)
            if doc is None:
                raise KeyError("That file is no longer in the list")
            if "selected" in payload:
                doc.selected = bool(payload["selected"])
            if "copies" in payload:
                copies = payload["copies"]
                if copies is None or copies == "":
                    doc.copies = None
                else:
                    copies = int(copies)
                    if not 1 <= copies <= 99:
                        raise ValueError("Copies must be from 1 to 99")
                    doc.copies = copies
            if "range" in payload:
                spec = str(payload["range"] or "").strip() or "all"
                if len(spec) > 80:
                    raise ValueError("That page range is too long")
                doc.range_spec = spec
            self._write_state()

    def select_all(self, selected: bool) -> None:
        self._require_idle()
        with self.lock:
            for doc in self.documents:
                doc.selected = bool(selected)
            self._write_state()

    def remove_documents(self, ids: list[str]) -> None:
        self._require_idle()
        wanted = {str(doc_id) for doc_id in ids}
        with self.lock:
            self.documents = [doc for doc in self.documents if doc.id not in wanted]
            self._write_state()

    def remove_printed(self) -> int:
        self._require_idle()
        with self.lock:
            before = len(self.documents)
            self.documents = [doc for doc in self.documents if doc.status != "printed"]
            removed = before - len(self.documents)
            self._write_state()
        if removed == 0:
            self._set_notice("No printed files to remove.")
        else:
            noun = "file" if removed == 1 else "files"
            self._set_notice(f"Removed {removed} printed {noun} from the list. They are still on disk.")
        return removed

    def clear(self) -> None:
        self._require_idle()
        with self.lock:
            self.documents.clear()
            self.job = Job()
            self._write_state()
        self._set_notice("Cleared the list. Files were left on disk.")

    def discard_list(self) -> None:
        """Drop the print list when the app closes. Settings stay on disk."""
        with self.lock:
            self._list_discarded = True
            self.documents.clear()
            self._write_state()

    def update_settings(self, patch: dict) -> None:
        with self.lock:
            previous = copy.deepcopy(self.settings)
            self.settings = apply_settings(self.settings, patch)
            printer_changed = self.settings["printer"] != previous["printer"]
            if printer_changed and self.settings.get("adopt_printer_defaults") and self.settings["printer"]:
                # Keep paper and tray on the printer default; copy color, sides, and copies.
                adopted = self._defaults_for_printer(self.settings["printer"])
                adopted["paper"] = "default"
                adopted["paper_tray"] = "default"
                self.settings = apply_settings(self.settings, adopted)
            paper_changed = (
                self.settings["paper"] != previous["paper"]
                or self.settings["orientation"] != previous["orientation"]
                or self.settings.get("custom_paper_width") != previous.get("custom_paper_width")
                or self.settings.get("custom_paper_height") != previous.get("custom_paper_height")
            )
            text_ids = [doc.id for doc in self.documents if doc.kind == "text"] if paper_changed else []
            for doc in self.documents:
                if doc.id in text_ids:
                    doc.inspecting = True
                    doc.pages = None
            self.preview_cache.clear()
            self._write_state()
        for doc_id in text_ids:
            self.executor.submit(self._inspect, doc_id)

    def adopt_printer_defaults(self) -> dict:
        """Pull paper/color/duplex/orientation from the selected printer."""
        with self.lock:
            printer = self.settings["printer"]
        if not printer:
            raise ValueError("Choose a printer first")
        defaults = self._defaults_for_printer(printer)
        if not any(defaults.values()):
            raise ValueError("This printer did not report usable defaults")
        self.update_settings(defaults)
        self._set_notice("Loaded paper and color settings from the printer.")
        return defaults

    def pick_printed_folder(self) -> dict:
        paths = self._choose("folder")
        if not paths:
            return {"cancelled": True}
        folder = paths[0]
        self.update_settings({"printed_folder": folder})
        return {"path": folder}

    def reset_settings(self) -> None:
        with self.lock:
            printer = self.settings.get("printer", "")
            width = self.settings.get("window_width", DEFAULT_SETTINGS["window_width"])
            height = self.settings.get("window_height", DEFAULT_SETTINGS["window_height"])
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            self.settings["printer"] = printer
            self.settings["window_width"] = width
            self.settings["window_height"] = height
            self.preview_cache.clear()
            self._write_state()
        self._set_notice("Settings were reset.")

    def export_settings(self) -> dict:
        paths = self._choose("save_preset")
        if not paths:
            return {"cancelled": True}
        path = Path(paths[0])
        if path.suffix.lower() != ".jpset":
            path = path.with_suffix(".jpset")
        payload = self._preset_payload()
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._set_notice(f"Saved settings to {path.name}.")
        return {"path": str(path)}

    def import_settings(self) -> dict:
        paths = self._choose("open_preset")
        if not paths:
            return {"cancelled": True}
        path = Path(paths[0])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read that settings file ({exc})") from exc
        patch = self._preset_to_patch(data)
        # Saved files may omit paper and tray when those stay on the printer default.
        if "paper" not in patch:
            patch["paper"] = "default"
        if "paper_tray" not in patch and "paperTray" not in patch:
            patch["paper_tray"] = "default"
        with self.lock:
            previous_adopt = bool(self.settings.get("adopt_printer_defaults"))
            self.settings["adopt_printer_defaults"] = False
        try:
            self.update_settings(patch)
        finally:
            if "adopt_printer_defaults" not in patch and "adoptPrinterDefaults" not in patch:
                with self.lock:
                    self.settings["adopt_printer_defaults"] = previous_adopt
                    self._write_state()
        self._set_notice(f"Loaded settings from {path.name}.")
        return {"path": str(path)}

    def save_window_size(self, width: int, height: int) -> None:
        self.update_settings({"window_width": int(width), "window_height": int(height)})

    def dismiss_summary(self) -> None:
        with self.lock:
            self.last_summary = None

    def start_print(self) -> None:
        self._start(test_page=False)

    def start_test_page(self) -> None:
        self._start(test_page=True)

    def stop(self) -> None:
        with self.lock:
            if not self.job.running:
                return
            self.stop_event.set()
            self.job.phase = "stopping"
            self.job.message = "Stopping…"

    def preview_png(self, doc_id: str, page: int) -> bytes | None:
        with self.lock:
            doc = self._doc(doc_id)
            if doc is None:
                return None
            path = doc.path
            modified = doc.modified
            settings = copy.deepcopy(self.settings)
            known_pages = doc.pages
        if page < 1 or (known_pages is not None and page > known_pages):
            return None
        key = (path, modified, page, settings["paper"], settings["orientation"], settings["color"])
        with self.preview_lock:
            cached = self.preview_cache.get(key)
            if cached is not None:
                return cached
        source = open_source(path, settings)
        try:
            if page > source.page_count:
                return None
            image = prepare(source.render(page - 1, "preview"), settings)
            image = decorate_page(image, settings, page=page, page_count=source.page_count, name=Path(path).name)
        finally:
            source.close()
        image.thumbnail((800, 1040), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        with self.preview_lock:
            self.preview_cache[key] = data
            while len(self.preview_cache) > 24:
                del self.preview_cache[next(iter(self.preview_cache))]
        return data

    def get_state(self) -> dict:
        with self.lock:
            documents = [self._public_document(doc) for doc in self.documents]
            settings = self._public_settings()
            job = self._public_job()
            totals, blocked = self._totals_locked()
            notice = self.notice if time.time() < self.notice_until else ""
            printer_name = self.settings["printer"]
            drop_tick = self.drop_tick
            pending_warning = self.pending_warning
        return {
            "documents": documents,
            "settings": settings,
            "job": job,
            "totals": totals,
            "blocked": blocked,
            "notice": notice,
            "dropTick": drop_tick,
            "warning": pending_warning,
            "summary": copy.deepcopy(self.last_summary),
            "printers": self._printer_names_cached(printer_name),
            "printerStatus": self._status_cached(printer_name),
        }

    def _start(self, test_page: bool) -> None:
        with self.lock:
            if self.job.running:
                raise RuntimeError("A print job is already running")
            if not test_page:
                blocked = self._blocked_locked()
                if blocked:
                    raise RuntimeError(blocked)
                if not any(doc.selected for doc in self.documents):
                    raise RuntimeError("Select at least one file")
            elif not self.settings["practice_run"] and not self.settings["printer"]:
                raise RuntimeError("Choose a printer first")
            if not self.settings["practice_run"] and not HAS_SPOOL:
                raise RuntimeError(SPOOL_ERROR or "Windows printing support is missing")
            self.stop_event.clear()
            self.notice = ""
            self.job = Job(running=True, phase="printing", message="Preparing the print job…")
            self.thread = threading.Thread(
                target=self._worker,
                args=(test_page,),
                name="justprint-job",
                daemon=True,
            )
            self.thread.start()

    def _worker(self, test_page: bool) -> None:
        settings = self._settings_copy()
        outcome = "done"
        errors = 0
        sink = None
        try:
            sink = make_sink(settings["printer"], settings, self.practice_delay, self.stop_event)
            if test_page:
                outcome = self._run_test_page(sink, settings)
            else:
                outcome, errors = self._run_documents(sink, settings)
        except SpoolError as exc:
            outcome = "error"
            self._set_job(message=str(exc))
            print(f"JustPrint: {exc}", flush=True)
        except Exception as exc:
            outcome = "error"
            self._set_job(message=f"Print failed: {exc}")
            traceback.print_exc()
        finally:
            if sink is not None:
                try:
                    sink.close()
                except Exception:
                    traceback.print_exc()
            try:
                self._finish(settings, outcome, errors, test_page)
            except Exception:
                traceback.print_exc()
                with self.lock:
                    self.job.running = False
                    self.job.phase = "error"
                    self.job.message = "Print failed."

    def _run_test_page(self, sink, settings: dict) -> str:
        self._set_job(
            file_index=1,
            file_total=1,
            sheets_total=1,
            sheets_printed=0,
            current_id=None,
            current_name="Test page",
            current_page=1,
            current_pages=1,
            message="Sending the test page…",
        )
        if self.stop_event.is_set():
            return "stopped"
        image = prepare(render_test_page(settings), settings)
        orientation = orientation_for(image, settings["orientation"])
        sink.begin_document("JustPrint test page", orientation, settings)
        started = True
        try:
            sent = sink.draw(image, orientation)
            if not sent or self.stop_event.is_set():
                self._commit(sink)
                return "stopped"
            sink.end_document()
            started = False
            self._set_job(sheets_printed=1, message=self._queue_status(settings))
            if not self._await_job(sink, settings, "Test page", expected_pages=1):
                return "stopped"
            return "done"
        except Exception:
            if started:
                sink.abort()
            raise

    def _run_documents(self, sink, settings: dict) -> tuple[str, int]:
        with self.lock:
            items: list[WorkItem] = []
            total = 0
            for doc in self.documents:
                if not doc.selected or doc.pages is None:
                    continue
                range_spec = self._effective_range(doc, settings)
                page_nums = filter_pages(parse_range(range_spec, doc.pages), settings)
                copies = doc.copies or settings["default_copies"]
                total += physical_sheets_for_settings(len(page_nums), copies, settings)
                items.append(WorkItem(doc.id, doc.path, doc.name, copies, range_spec))
                doc.status = "ready"
                doc.error = None
            repeats = max(1, int(settings.get("batch_repeat") or 1))
            self.job.file_total = len(items)
            self.job.file_index = 0
            self.job.sheets_total = total * repeats + self._cover_sheet_estimate(items, settings, repeats)
            self.job.sheets_printed = 0
            self.job.message = self._sending_message(settings)
            self.last_summary = None
        if not items:
            return "done", 0
        if settings.get("single_job"):
            errors = 0
            for repeat in range(repeats):
                if self.stop_event.is_set():
                    return "stopped", errors
                if repeat > 0:
                    self._pause_between_files(settings)
                    if self.stop_event.is_set():
                        return "stopped", errors
                outcome, err = self._run_documents_single_job(
                    sink, settings, items, end_cover=repeat == repeats - 1
                )
                errors += err
                if outcome == "stopped":
                    return "stopped", errors
            return "done", errors
        errors = 0
        counter = SheetProgress(settings["duplex"] != "simplex")
        self._last_cover_folder = None
        for repeat in range(repeats):
            self._last_cover_folder = None
            for index, item in enumerate(items, start=1):
                if self.stop_event.is_set():
                    self._set_job(sheets_printed=counter.physical)
                    return "stopped", errors
                if not (repeat == 0 and index == 1):
                    self._pause_between_files(settings)
                    if self.stop_event.is_set():
                        self._set_job(sheets_printed=counter.physical)
                        return "stopped", errors
                try:
                    self._print_one(sink, settings, item, counter, index, shared_doc=False)
                except StopPrint:
                    self._mark(item.id, "stopped", "Stopped before this file finished")
                    self._set_job(sheets_printed=counter.physical)
                    return "stopped", errors
                except SpoolError:
                    self._mark(item.id, "error", "The printer stopped accepting pages")
                    raise
                except Exception as exc:
                    errors += 1
                    self._mark(item.id, "error", str(exc))
                    continue
                else:
                    doc = self._doc(item.id)
                    if doc is None or doc.status != "error":
                        self._mark(item.id, "printed", None)
        if settings.get("end_cover_page") and not self.stop_event.is_set():
            self._emit_special_sheet(
                sink,
                settings,
                items[-1],
                counter,
                labeled_separator(settings, "End of print list"),
                shared_doc=False,
            )
        self._set_job(sheets_printed=counter.physical)
        return "done", errors

    def _run_documents_single_job(
        self, sink, settings: dict, items: list[WorkItem], *, end_cover: bool = False
    ) -> tuple[str, int]:
        """Send every selected file inside one Windows spool document."""
        if not items:
            return "done", 0
        errors = 0
        counter = SheetProgress(settings["duplex"] != "simplex")
        expected_pages = 0
        started = False
        self._last_cover_folder = None
        try:
            first_item = items[0]
            self._set_job(
                file_index=1,
                current_id=first_item.id,
                current_name=first_item.name,
                message=self._sending_message(settings),
            )
            self._mark(first_item.id, "preparing", None)
            probe_error = None
            try:
                probe = open_source(first_item.path, settings)
            except Exception as exc:
                probe_error = exc
            else:
                try:
                    probe_pages = parse_range(first_item.range_spec, probe.page_count)
                    probe_group = next(
                        iter_groups(
                            probe_pages,
                            first_item.copies,
                            duplex=settings["duplex"],
                            collate=settings["collate"],
                        )
                    )
                    probe_image = prepare(probe.render(probe_group[0] - 1, "print"), settings)
                    sink.begin_document("JustPrint", orientation_for(probe_image, settings["orientation"]), settings)
                    started = True
                finally:
                    probe.close()
            if not started:
                if not settings.get("placeholder"):
                    if probe_error is not None:
                        raise probe_error
                    raise RenderError(f"Could not open {first_item.name}")
                stand_in = prepare(labeled_separator(settings, f"Missing · {first_item.name}"), settings)
                sink.begin_document("JustPrint", orientation_for(stand_in, settings["orientation"]), settings)
                started = True

            for index, item in enumerate(items, start=1):
                if self.stop_event.is_set():
                    raise StopPrint()
                try:
                    pages_sent = self._print_one(sink, settings, item, counter, index, shared_doc=True)
                    expected_pages += pages_sent
                    expected_pages += self._pad_document_front(sink, settings, item, counter, pages_sent)
                    with self.lock:
                        doc = self._doc(item.id)
                        failed = doc is not None and doc.status == "error"
                    if not failed:
                        self._mark(item.id, "queued", None)
                except StopPrint:
                    raise
                except SpoolError:
                    self._mark(item.id, "error", "The printer stopped accepting pages")
                    raise
                except Exception as exc:
                    errors += 1
                    self._mark(item.id, "error", str(exc))

            if started and end_cover and settings.get("end_cover_page"):
                expected_pages += self._emit_special_sheet(
                    sink,
                    settings,
                    items[-1],
                    counter,
                    labeled_separator(settings, "End of print list"),
                    shared_doc=True,
                )
            if started:
                sink.end_document()
                started = False
                for item in items:
                    with self.lock:
                        doc = self._doc(item.id)
                        if doc and doc.status == "queued":
                            doc.status = "printing"
                self._set_job(message=self._queue_status(settings))
                if settings.get("wait_for_empty_queue", True):
                    if not self._await_job(sink, settings, "batch", expected_pages=max(1, expected_pages)):
                        raise StopPrint()
                for item in items:
                    with self.lock:
                        doc = self._doc(item.id)
                        if doc and doc.status in {"queued", "printing", "preparing"}:
                            doc.status = "printed"
                            doc.error = None
            self._set_job(sheets_printed=counter.physical)
            return "done", errors
        except StopPrint:
            if started:
                self._commit(sink)
            for item in items:
                with self.lock:
                    doc = self._doc(item.id)
                    if doc and doc.status in {"preparing", "queued", "printing"}:
                        doc.status = "stopped"
                        doc.error = "Stopped before this file finished"
            self._set_job(sheets_printed=counter.physical)
            return "stopped", errors
        except Exception:
            if started:
                sink.abort()
            raise

    def _print_one(
        self,
        sink,
        settings: dict,
        item: WorkItem,
        counter: SheetProgress,
        file_index: int,
        *,
        shared_doc: bool,
    ) -> int:
        self._set_job(
            file_index=file_index,
            current_id=item.id,
            current_name=item.name,
            current_page=1,
            device_pages_printed=0,
            device_pages_total=0,
            message=self._sending_message(settings),
        )
        self._mark(item.id, "preparing", None)
        pages_sent = 0
        source = None
        try:
            pages_sent += self._emit_folder_cover(sink, settings, item, counter, shared_doc=shared_doc)
            if settings.get("cover_page") and not shared_doc:
                pages_sent += self._emit_special_sheet(
                    sink, settings, item, counter, labeled_separator(settings, item.name), shared_doc=shared_doc
                )
            try:
                source = open_source(item.path, settings)
            except Exception as exc:
                if not settings.get("placeholder"):
                    raise
                pages_sent += self._emit_special_sheet(
                    sink,
                    settings,
                    item,
                    counter,
                    labeled_separator(settings, f"Missing · {item.name}"),
                    shared_doc=shared_doc,
                )
                self._mark(item.id, "error", str(exc))
                return pages_sent
            with self.lock:
                doc = self._doc(item.id)
                if doc is not None:
                    doc.pages = source.page_count
                self.job.current_pages = source.page_count
            page_nums = filter_pages(parse_range(item.range_spec, source.page_count), settings)
            page_nums = self._drop_blank_pages(source, settings, page_nums)
            sheet_groups = sheet_page_groups(page_nums, settings)
            use_sheets = bool(settings.get("booklet")) or int(settings.get("n_up") or 1) > 1
            if use_sheets:
                for _copy in range(max(1, item.copies)):
                    for sheet_pages in sheet_groups:
                        if self.stop_event.is_set():
                            raise StopPrint()
                        pages_sent += self._print_sheet(
                            sink, settings, item, counter, source, sheet_pages, shared_doc=shared_doc
                        )
            else:
                for group in iter_groups(page_nums, item.copies, duplex=settings["duplex"], collate=settings["collate"]):
                    if self.stop_event.is_set():
                        raise StopPrint()
                    pages_sent += self._print_group(
                        sink,
                        settings,
                        item,
                        counter,
                        source,
                        group,
                        shared_doc=shared_doc,
                    )
            if settings.get("separator_pages") and not shared_doc:
                pages_sent += self._emit_special_sheet(
                    sink, settings, item, counter, labeled_separator(settings, f"End · {item.name}"), shared_doc=False
                )
        finally:
            if source is not None:
                source.close()
        return pages_sent

    def _cover_sheet_estimate(self, items: list[WorkItem], settings: dict, repeats: int) -> int:
        if not items:
            return 0
        faces = 0
        if settings.get("folder_cover_page"):
            for _repeat in range(max(1, repeats)):
                last = None
                for item in items:
                    folder = os.path.dirname(os.path.abspath(item.path))
                    if folder != last:
                        faces += 1
                        last = folder
        if settings.get("end_cover_page"):
            faces += 1
        if settings.get("duplex", "simplex") == "simplex":
            return faces
        return (faces + 1) // 2

    def _emit_folder_cover(self, sink, settings, item: WorkItem, counter: SheetProgress, *, shared_doc: bool) -> int:
        if not settings.get("folder_cover_page"):
            return 0
        folder = os.path.dirname(os.path.abspath(item.path))
        if folder == getattr(self, "_last_cover_folder", None):
            return 0
        self._last_cover_folder = folder
        title = os.path.basename(folder) or folder
        return self._emit_special_sheet(
            sink, settings, item, counter, labeled_separator(settings, title), shared_doc=shared_doc
        )

    def _page_image(self, source, settings: dict, page: int, name: str):
        label = os.path.basename(name) or name
        try:
            return prepare(source.render(page - 1, "print"), settings)
        except Exception:
            if not settings.get("placeholder"):
                raise
            return prepare(labeled_separator(settings, f"Missing page {page} · {label}"), settings)

    def _drop_blank_pages(self, source, settings: dict, page_nums: list[int]) -> list[int]:
        if not settings.get("skip_blank"):
            return page_nums
        kept: list[int] = []
        for page in page_nums:
            image = self._page_image(source, settings, page, source.path)
            if not is_blank_page(image):
                kept.append(page)
        return kept

    def _emit_special_sheet(self, sink, settings, item: WorkItem, counter: SheetProgress, image, *, shared_doc: bool) -> int:
        started = False
        try:
            image = prepare(image, settings)
            image = decorate_page(image, settings, page=1, page_count=1, name=item.name)
            if not shared_doc:
                sink.begin_document(f"{item.name} · cover", orientation_for(image, settings["orientation"]), settings)
                started = True
            sent = sink.draw(image, orientation_for(image, settings["orientation"]))
            if not sent:
                raise StopPrint()
            counter.side_sent()
            if started:
                sink.end_document()
                started = False
            self._set_job(sheets_printed=counter.physical)
            return 1
        except StopPrint:
            if started:
                sink.abort()
            raise

    def _print_sheet(self, sink, settings, item: WorkItem, counter: SheetProgress, source, sheet_pages: list[int], *, shared_doc: bool) -> int:
        """Print one n-up / booklet face."""
        started = False
        images: list = []
        for page in sheet_pages:
            if page <= 0:
                images.append(None)
                continue
            raw = self._page_image(source, settings, page, item.name)
            images.append(decorate_page(raw, settings, page=page, page_count=source.page_count, name=item.name))
        sheet = compose_nup(images, settings)
        try:
            if not shared_doc:
                sink.begin_document(item.name, orientation_for(sheet, settings["orientation"]), settings)
                started = True
            self._mark(item.id, "preparing", None)
            first_page = next((p for p in sheet_pages if p > 0), 1)
            self._set_job(current_page=first_page, current_pages=source.page_count, message=self._sending_message(settings))
            sent = sink.draw(sheet, orientation_for(sheet, settings["orientation"]))
            if not sent:
                raise StopPrint()
            counter.side_sent()
            drawn = 1
            if not shared_doc:
                sink.end_document()
                started = False
                self._mark(item.id, "queued", None)
                self._set_job(message=self._queue_status(settings))
                if settings.get("wait_for_empty_queue", True):
                    self._mark(item.id, "printing", None)
                    if not self._await_job(sink, settings, item.name, expected_pages=1):
                        raise StopPrint()
                else:
                    self._mark(item.id, "printing", None)
            return drawn
        except StopPrint:
            if started:
                sink.abort()
            raise
        finally:
            counter.end_copy()
            self._set_job(sheets_printed=counter.physical)

    def _print_group(
        self,
        sink,
        settings,
        item: WorkItem,
        counter: SheetProgress,
        source,
        group: list[int],
        *,
        shared_doc: bool,
    ) -> int:
        started = False
        drawn = 0
        try:
            if self.stop_event.is_set():
                raise StopPrint()
            first = self._page_image(source, settings, group[0], item.name)
            if not shared_doc:
                sink.begin_document(item.name, orientation_for(first, settings["orientation"]), settings)
                started = True
            self._mark(item.id, "preparing", None)
            first = decorate_page(first, settings, page=group[0], page_count=source.page_count, name=item.name)
            self._emit_page(sink, settings, item, counter, source, group[0], first)
            drawn += 1
            for page in group[1:]:
                if self.stop_event.is_set():
                    raise StopPrint()
                image = self._page_image(source, settings, page, item.name)
                image = decorate_page(image, settings, page=page, page_count=source.page_count, name=item.name)
                self._emit_page(sink, settings, item, counter, source, page, image)
                drawn += 1
            if not shared_doc:
                sink.end_document()
                started = False
                self._mark(item.id, "queued", None)
                self._set_job(message=self._queue_status(settings))
                if settings.get("wait_for_empty_queue", True):
                    self._mark(item.id, "printing", None)
                    if not self._await_job(sink, settings, item.name, expected_pages=len(group)):
                        raise StopPrint()
                else:
                    self._mark(item.id, "printing", None)
            return drawn
        except StopPrint:
            if started:
                if drawn:
                    self._commit(sink)
                else:
                    sink.abort()
            raise
        except SpoolError:
            if started:
                sink.abort()
            raise
        except Exception:
            if started:
                if drawn:
                    self._commit(sink)
                else:
                    sink.abort()
            raise
        finally:
            counter.end_copy()
            self._set_job(sheets_printed=counter.physical)

    def _emit_page(self, sink, settings, item: WorkItem, counter: SheetProgress, source, page: int, image) -> None:
        self._set_job(
            current_id=item.id,
            current_name=item.name,
            current_page=page,
            current_pages=source.page_count,
            message=self._sending_message(settings),
        )
        sent = sink.draw(image, orientation_for(image, settings["orientation"]))
        if not sent:
            raise StopPrint()
        counter.side_sent()
        self._set_job(sheets_printed=counter.physical)

    def _commit(self, sink) -> None:
        try:
            sink.end_document()
        except Exception:
            sink.abort()

    def _pause_between_files(self, settings: dict) -> None:
        seconds = int(settings.get("pause_before_document") or 0)
        if seconds <= 0:
            return
        self._set_job(message=f"Pausing {seconds}s before the next file…")
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.stop_event.wait(0.2):
                return

    def _pad_document_front(self, sink, settings: dict, item: WorkItem, counter: SheetProgress, pages_sent: int) -> int:
        """In a shared duplex job, pad an odd page count so the next file starts on a front."""
        if settings.get("duplex") == "simplex":
            return 0
        if not settings.get("document_on_front", True):
            return 0
        if pages_sent <= 0 or pages_sent % 2 == 0:
            return 0
        from justprint.render import blank_page

        image = blank_page(settings)
        sent = sink.draw(image, orientation_for(image, settings["orientation"]))
        if not sent:
            raise StopPrint()
        counter.side_sent()
        self._set_job(sheets_printed=counter.physical, message=f"Padding sheet after {item.name}…")
        return 1

    def _effective_range(self, doc: Document, settings: dict) -> str:
        global_range = str(settings.get("page_range") or "").strip()
        if global_range:
            return global_range
        return doc.range_spec

    def _await_job(self, sink, settings: dict, name: str, expected_pages: int = 0) -> bool:
        """Wait until the printer finishes the job just sent. False if Stop was pressed."""
        expected = max(0, int(expected_pages or 0))
        ppm = float(settings.get("sheets_per_minute", 0) or 0)

        def on_status(info: dict) -> None:
            pages = int(info.get("pagesPrinted") or 0)
            total = max(int(info.get("totalPages") or 0), expected)
            label = str(info.get("label") or "Printing")
            if settings.get("practice_run") and label == "Printing":
                label = "Practice run"
            if total > 0:
                detail = f"{label} · page {min(pages, total)} of {total}"
            else:
                detail = label
            self._set_job(
                message=detail,
                device_pages_printed=pages,
                device_pages_total=total,
            )

        return bool(sink.wait_for_job(on_status, expected_pages=expected, sheets_per_minute=ppm))

    def _finish(self, settings: dict, outcome: str, errors: int, test_page: bool) -> None:
        actions_note = ""
        report_snapshot: dict | None = None
        if not test_page and outcome in {"done", "errors", "stopped"}:
            actions_note = self._apply_after_print(settings)
        with self.lock:
            printed_sheets = self.job.sheets_printed
            practice = bool(settings.get("practice_run"))
            docs = [
                {
                    "name": doc.name,
                    "status": doc.status,
                    "error": doc.error or "",
                }
                for doc in self.documents
            ]
            printed_files = sum(1 for doc in self.documents if doc.status == "printed")
            failed_files = sum(1 for doc in self.documents if doc.status == "error")
            stopped_files = sum(1 for doc in self.documents if doc.status == "stopped")
            if outcome == "error":
                phase = "error"
                message = self.job.message or "Print failed."
            elif outcome == "stopped" or self.stop_event.is_set():
                phase = "stopped"
                message = _summary(practice, "stopped", printed_sheets, test_page)
            elif errors:
                phase = "done"
                message = _summary(practice, "errors", printed_sheets, test_page)
            else:
                phase = "done"
                message = _summary(practice, "done", printed_sheets, test_page)
            if actions_note:
                message = f"{message} {actions_note}".strip()
            summary = None
            if settings.get("show_summary") and not test_page:
                summary = {
                    "title": "Print summary",
                    "message": message,
                    "sheets": printed_sheets,
                    "printed": printed_files,
                    "failed": failed_files,
                    "stopped": stopped_files,
                    "practice": practice,
                    "items": docs,
                }
            if settings.get("print_report") and summary is not None:
                summary["title"] = "Print report"
            self.job.running = False
            self.job.phase = phase
            self.job.message = message
            self.job.current_id = None
            self.last_summary = summary
            report_snapshot = copy.deepcopy(summary) if summary else {
                "message": message,
                "sheets": printed_sheets,
                "printed": printed_files,
                "failed": failed_files,
                "stopped": stopped_files,
                "items": docs,
            }
        if not test_page and settings.get("report_file") and outcome in {"done", "errors", "stopped"}:
            note = self._write_report(settings, report_snapshot)
            if note:
                with self.lock:
                    self.job.message = f"{self.job.message} {note}".strip()
                    if self.last_summary is not None:
                        self.last_summary["message"] = self.job.message
        removed = 0
        if not test_page and settings.get("remove_printed_after") and outcome in {"done", "errors"}:
            try:
                removed = self.remove_printed()
            except RuntimeError:
                removed = 0
            if removed:
                with self.lock:
                    self.job.message = f"{self.job.message} Removed {removed} printed from the list."
                    if self.last_summary is not None:
                        self.last_summary["message"] = self.job.message

    def _inspect(self, doc_id: str) -> None:
        with self.lock:
            doc = self._doc(doc_id)
            if doc is None:
                return
            path = doc.path
            settings = copy.deepcopy(self.settings)
        try:
            pages = inspect_pages(path, settings)
            error = None
        except Exception as exc:
            pages = None
            error = str(exc)
        with self.lock:
            doc = self._doc(doc_id)
            if doc is None:
                return
            doc.pages = pages
            doc.inspecting = False
            if error:
                doc.error = error
                if doc.status in {"ready", "error"}:
                    doc.status = "error"
            elif doc.status == "error":
                doc.status = "ready"
                doc.error = None

    def _queue_locked(self, path: str, existing: set[str]) -> str:
        full = os.path.abspath(path)
        key = os.path.normcase(full)
        if key in existing:
            return "duplicate"
        if not is_allowed(full, self.settings):
            return "unsupported"
        try:
            info = os.stat(full)
        except OSError:
            return "unsupported"
        kind, label = classify(full)
        doc = Document(
            id=uuid.uuid4().hex,
            path=full,
            name=os.path.basename(full),
            kind=kind,
            type_label=label,
            pages=None,
            size=info.st_size,
            modified=info.st_mtime,
            copies=None,
            range_spec="all",
            selected=True,
            status="ready",
            error=None,
            inspecting=True,
        )
        self.documents.append(doc)
        existing.add(key)
        return doc.id

    def _choose(self, kind: str) -> list[str]:
        window = self.window
        if window is not None:
            try:
                return _webview_choose(window, kind)
            except Exception as exc:
                print(f"JustPrint dialog: {exc}", flush=True)
        try:
            return self._dialogs.ask(kind)
        except Exception as exc:
            raise RuntimeError(f"Could not open the file window ({exc})") from exc

    def _require_idle(self) -> None:
        with self.lock:
            if self.job.running:
                raise RuntimeError("Wait until this job finishes, or press Stop")

    def _settings_copy(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.settings)

    def _doc(self, doc_id: str) -> Document | None:
        for doc in self.documents:
            if doc.id == doc_id:
                return doc
        return None

    def _mark(self, doc_id: str, status: str, error: str | None) -> None:
        with self.lock:
            doc = self._doc(doc_id)
            if doc is None:
                return
            doc.status = status
            doc.error = error

    def _set_job(self, **kwargs) -> None:
        with self.lock:
            for key, value in kwargs.items():
                setattr(self.job, key, value)

    def _set_notice(self, message: str, seconds: float = 8.0) -> None:
        with self.lock:
            self.notice = message
            self.notice_until = time.time() + seconds

    def _sending_message(self, settings: dict) -> str:
        if settings.get("practice_run"):
            return "Practice run. Nothing is being sent to the printer."
        return "Sending pages to the printer…"

    def _queue_status(self, settings: dict) -> str:
        if settings.get("practice_run"):
            return "Practice run. Nothing is being sent to the printer."
        return "Printing…"

    def _blocked_locked(self) -> str:
        return self._totals_locked()[1]

    def _totals_locked(self) -> tuple[dict, str]:
        pages = 0
        sheets = 0
        selected = 0
        blocked = ""
        for doc in self.documents:
            if not doc.selected:
                continue
            selected += 1
            if not blocked and doc.inspecting:
                blocked = "Still reading files…"
            if doc.pages is None:
                if not blocked and doc.error:
                    blocked = f"{doc.name}: {doc.error}"
                continue
            try:
                page_nums = filter_pages(
                    parse_range(self._effective_range(doc, self.settings), doc.pages),
                    self.settings,
                )
                count = len(page_nums)
            except ValueError as exc:
                if not blocked:
                    blocked = f"{doc.name}: {exc}"
                continue
            copies = doc.copies or int(self.settings["default_copies"])
            pages += count
            sheets += physical_sheets_for_settings(count, copies, self.settings)
        repeats = max(1, int(self.settings.get("batch_repeat") or 1))
        pages *= repeats
        sheets *= repeats
        if selected == 0 and not blocked:
            blocked = "Select at least one file." if self.documents else "Add a file to print."
        if selected and not self.settings["practice_run"] and not self.settings["printer"] and not blocked:
            blocked = "Choose a printer first."
        if selected and not self.settings["practice_run"] and not HAS_SPOOL and not blocked:
            blocked = SPOOL_ERROR or "Windows printing support is missing."
        if str(self.settings.get("page_range") or "").strip() and not blocked:
            try:
                _validate_range_syntax(self.settings["page_range"])
            except ValueError as exc:
                blocked = f"Page range: {exc}"
        totals = {
            "sheets": sheets,
            "pages": pages,
            "files": len(self.documents),
            "selected": selected,
        }
        return totals, blocked

    def _public_document(self, doc: Document) -> dict:
        return {
            "id": doc.id,
            "path": doc.path,
            "name": doc.name,
            "kind": doc.kind,
            "typeLabel": doc.type_label,
            "pages": doc.pages,
            "size": doc.size,
            "modified": doc.modified,
            "copies": doc.copies,
            "range": doc.range_spec,
            "rangeError": _range_error(doc),
            "selected": doc.selected,
            "status": doc.status,
            "error": doc.error,
            "inspecting": doc.inspecting,
        }

    def _public_settings(self) -> dict:
        settings = self.settings
        base = {
            "printer": settings["printer"],
            "paper": settings["paper"],
            "paperTray": settings.get("paper_tray", "default"),
            "orientation": settings["orientation"],
            "color": settings["color"],
            "duplex": settings["duplex"],
            "defaultCopies": settings["default_copies"],
            "collate": settings["collate"],
            "batchRepeat": settings.get("batch_repeat", 1),
            "pageRange": settings.get("page_range", ""),
            "documentOnFront": settings.get("document_on_front", True),
            "customPaperWidth": settings.get("custom_paper_width", 0),
            "customPaperHeight": settings.get("custom_paper_height", 0),
            "subfolders": settings["subfolders"],
            "types": dict(settings["types"]),
            "practiceRun": settings["practice_run"],
            "singleJob": settings["single_job"],
            "pauseBeforeDocument": settings["pause_before_document"],
            "waitForEmptyQueue": settings["wait_for_empty_queue"],
            "sheetsPerMinute": settings["sheets_per_minute"],
            "removePrintedAfter": settings["remove_printed_after"],
            "showSummary": settings["show_summary"],
            "printedAction": settings["printed_action"],
            "printedFolder": settings["printed_folder"],
            "adoptPrinterDefaults": settings["adopt_printer_defaults"],
            "windowWidth": settings["window_width"],
            "windowHeight": settings["window_height"],
        }
        base.update(public_option_settings(settings))
        return base

    def _preset_payload(self) -> dict:
        settings = self._settings_copy()
        preset = {
            "copies": settings["default_copies"],
            "collate": settings["collate"],
            "batchRepeat": settings.get("batch_repeat", 1),
            "orientation": str(settings["orientation"]).title() if settings["orientation"] != "auto" else "Auto",
            "duplex": {"simplex": "None", "long": "Long", "short": "Short"}.get(settings["duplex"], "None"),
            "range": settings.get("page_range", ""),
            "monochrome": settings["color"] == "grayscale",
            "singleJob": settings["single_job"],
            "pauseBeforeDocument": settings["pause_before_document"],
            "waitForEmptyQueue": settings["wait_for_empty_queue"],
            "printerSheetsPerMinute": settings["sheets_per_minute"],
            "showSummary": settings["show_summary"],
            "removePrinted": settings["remove_printed_after"],
            "paper": settings["paper"],
            "paperTray": settings.get("paper_tray", "default"),
            "printedAction": settings["printed_action"],
            "printedFolder": settings["printed_folder"],
            "subfolders": settings["subfolders"],
            "types": dict(settings["types"]),
            "adoptPrinterDefaults": settings["adopt_printer_defaults"],
        }
        preset.update(preset_option_block(settings))
        return {
            "format": "justprint-settings",
            "schemaVersion": 1,
            "app": "1.0.0",
            "printer": settings.get("printer", ""),
            "preset": preset,
        }

    def _preset_to_patch(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("That settings file was not understood")
        patch: dict = {}
        if data.get("printer"):
            patch["printer"] = data["printer"]
        preset = data.get("preset") if isinstance(data.get("preset"), dict) else data
        if not isinstance(preset, dict):
            raise ValueError("That settings file was not understood")
        for key, value in preset.items():
            patch[key] = value
        orientation = patch.get("orientation")
        if isinstance(orientation, str):
            patch["orientation"] = orientation.strip().lower()
        for key in ("scale", "parity", "horizontalAlign", "verticalAlign", "nUpOrder", "bookletBinding", "reportFormat"):
            if isinstance(patch.get(key), str):
                patch[key] = patch[key].strip().lower()
        if isinstance(patch.get("nUpOrder"), str):
            patch["nUpOrder"] = patch["nUpOrder"].replace("_", "")
        patch.pop("practiceRun", None)
        patch.pop("practice_run", None)
        return patch

    def _defaults_for_printer(self, printer: str) -> dict:
        raw = printer_defaults(printer)
        patch: dict = {}
        if raw.get("paper") in PAPERS:
            patch["paper"] = raw["paper"]
        if raw.get("orientation") in {"portrait", "landscape"}:
            patch["orientation"] = raw["orientation"]
        if raw.get("color") in COLORS:
            patch["color"] = raw["color"]
        if raw.get("duplex") in DUPLEXES:
            patch["duplex"] = raw["duplex"]
        if raw.get("copies"):
            patch["default_copies"] = raw["copies"]
        return patch

    def _write_report(self, settings: dict, summary: dict | None) -> str:
        if not summary:
            return ""
        fmt = str(settings.get("report_format") or "text").lower()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        root = state_path().parent / "reports"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Could not write report ({exc})."
        path = root / f"print-report-{stamp}.{'html' if fmt == 'html' else 'txt'}"
        items = summary.get("items") or []
        if fmt == "html":
            rows = "".join(
                f"<tr><td>{_html(item.get('name'))}</td><td>{_html(item.get('status'))}</td>"
                f"<td>{_html(item.get('error'))}</td></tr>"
                for item in items
            )
            body = (
                "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Print report</title></head><body>"
                f"<h1>Print report</h1><p>{_html(summary.get('message'))}</p>"
                f"<p>Sheets: {summary.get('sheets', 0)} · Printed: {summary.get('printed', 0)} · "
                f"Failed: {summary.get('failed', 0)}</p>"
                f"<table border='1' cellpadding='4'><tr><th>File</th><th>Status</th><th>Error</th></tr>{rows}</table>"
                "</body></html>"
            )
        else:
            lines = [
                "JustPrint report",
                str(summary.get("message") or ""),
                f"Sheets: {summary.get('sheets', 0)}",
                f"Printed: {summary.get('printed', 0)}",
                f"Failed: {summary.get('failed', 0)}",
                f"Stopped: {summary.get('stopped', 0)}",
                "",
            ]
            for item in items:
                err = f" — {item.get('error')}" if item.get("error") else ""
                lines.append(f"{item.get('name')}: {item.get('status')}{err}")
            body = "\n".join(lines) + "\n"
        try:
            path.write_text(body, encoding="utf-8")
        except OSError as exc:
            return f"Could not write report ({exc})."
        return f"Report saved as {path.name}."

    def _apply_after_print(self, settings: dict) -> str:
        action = str(settings.get("printed_action") or "none")
        if action == "none" or settings.get("practice_run"):
            return ""
        folder = str(settings.get("printed_folder") or "").strip()
        if not folder:
            return "Printed-file folder is not set."
        try:
            root = Path(folder)
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return f"Could not use the printed-file folder ({exc})."
        moved = 0
        failed = 0
        with self.lock:
            targets = [doc for doc in self.documents if doc.status == "printed"]
        for doc in targets:
            try:
                source = Path(doc.path)
                if not source.is_file():
                    failed += 1
                    continue
                destination = root / source.name
                stem = destination.stem
                suffix = destination.suffix
                n = 1
                while destination.exists():
                    destination = root / f"{stem} ({n}){suffix}"
                    n += 1
                if action == "copy":
                    shutil.copy2(source, destination)
                else:
                    shutil.move(str(source), str(destination))
                    with self.lock:
                        current = self._doc(doc.id)
                        if current is not None:
                            current.path = str(destination)
                moved += 1
            except OSError:
                failed += 1
        if moved and action == "move":
            with self.lock:
                self._write_state()
        if moved and not failed:
            return f"{'Copied' if action == 'copy' else 'Moved'} {moved} printed file{'s' if moved != 1 else ''}."
        if moved and failed:
            return f"{'Copied' if action == 'copy' else 'Moved'} {moved}, failed {failed}."
        if failed:
            return f"Could not {'copy' if action == 'copy' else 'move'} printed files."
        return ""

    def _public_job(self) -> dict:
        job = self.job
        return {
            "running": job.running,
            "phase": job.phase,
            "message": job.message,
            "fileIndex": job.file_index,
            "fileTotal": job.file_total,
            "sheetsPrinted": job.sheets_printed,
            "sheetsTotal": job.sheets_total,
            "currentId": job.current_id,
            "currentName": job.current_name,
            "currentPage": job.current_page,
            "currentPages": job.current_pages,
            "devicePagesPrinted": job.device_pages_printed,
            "devicePagesTotal": job.device_pages_total,
        }

    def _printer_names_cached(self, selected: str) -> list[str]:
        now = time.time()
        if now - self._printer_names_at > 1.5 or not self._printer_names:
            self._printer_names = list_printers()
            self._printer_names_at = now
        names = list(self._printer_names)
        if selected and selected not in names:
            names.insert(0, selected)
        return names

    def _status_cached(self, name: str) -> dict:
        now = time.time()
        cached = self._status_cache.get(name)
        if cached and now - cached[0] < 1.5:
            return cached[1]
        status = printer_status(name)
        self._status_cache[name] = (now, status)
        return status

    def _load(self) -> None:
        path = state_path()
        data = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        incoming = data.get("settings")
        if isinstance(incoming, dict):
            try:
                self.settings = apply_settings(DEFAULT_SETTINGS, incoming)
            except (ValueError, TypeError):
                self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        merge_option_defaults(self.settings)
        self.settings["practice_run"] = False
        if not self.settings["printer"]:
            self.settings["printer"] = default_printer()
            if self.settings["printer"] and self.settings.get("adopt_printer_defaults"):
                adopted = self._defaults_for_printer(self.settings["printer"])
                adopted["paper"] = "default"
                adopted["paper_tray"] = "default"
                self.settings = apply_settings(self.settings, adopted)
        # The print list is session-only. Closing the app drops it from this file.

    def _write_state(self) -> None:
        documents = [] if self._list_discarded else [
            {
                "path": doc.path,
                "copies": doc.copies,
                "range": doc.range_spec,
                "selected": doc.selected,
            }
            for doc in self.documents
        ]
        payload = {
            "settings": self.settings,
            "documents": documents,
        }
        path = state_path()
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(path)


def _range_error(doc: Document) -> str | None:
    if doc.pages is None:
        return None
    try:
        parse_range(doc.range_spec, doc.pages)
    except ValueError as exc:
        return str(exc)
    return None


def _html(value) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _summary(practice: bool, kind: str, printed: int, test_page: bool) -> str:
    if test_page and kind == "done" and not practice:
        return "Test page sent."
    if test_page and kind == "done" and practice:
        return "Practice run: the test page was not sent to the printer."
    if test_page and kind == "stopped":
        if practice:
            return "Practice run stopped. The test page was not sent."
        return "Test page stopped."
    if practice:
        lead = {
            "done": "Practice run finished. Nothing was sent to the printer.",
            "stopped": "Practice run stopped. Nothing was sent to the printer.",
            "errors": "Practice run finished with errors. Nothing was sent to the printer.",
        }[kind]
        return f"{lead} Sheets counted: {printed}."
    lead = {"done": "Finished.", "stopped": "Stopped.", "errors": "Finished with errors."}[kind]
    return f"{lead} Sheets printed: {printed}."


def _added_message(
    added: int,
    duplicate: int,
    unsupported: int,
    missing: int,
    *,
    needs_pdf: int = 0,
    needs_pdf_names: list[str] | None = None,
) -> str:
    if added == 0 and duplicate == 0 and unsupported == 0 and missing == 0 and needs_pdf == 0:
        return "No supported files found."
    parts: list[str] = []
    if added:
        parts.append(f"Added {added} file" if added == 1 else f"Added {added} files")
    if duplicate:
        parts.append(f"{duplicate} already in the list")
    if unsupported:
        parts.append(f"{unsupported} not a supported type")
    if needs_pdf:
        names = needs_pdf_names or []
        listed = ", ".join(names)
        extra = needs_pdf - len(names)
        if extra > 0:
            listed = f"{listed}, and {extra} more" if listed else f"{extra} more"
        if needs_pdf == 1:
            detail = f" ({listed})" if listed else ""
            parts.append(
                f"skipped 1 unsupported file{detail} — convert it to PDF in its own app, then add the PDF"
            )
        else:
            detail = f" ({listed})" if listed else ""
            parts.append(
                f"skipped {needs_pdf} unsupported files{detail} — convert them to PDF in their own apps, then add the PDFs"
            )
    if missing:
        parts.append(f"{missing} not found")
    return ". ".join(parts) + "."


def _natural_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _is_skipped_name(name: str) -> bool:
    return name.startswith(".") or name.startswith("~$") or name.lower() in {"thumbs.db", "desktop.ini"}


def _scan_add_paths(roots: list[str], settings: dict) -> tuple[list[str], list[str], int, int]:
    """Return (natives, convertibles, missing, unsupported) from add roots."""
    natives: list[str] = []
    convertibles: list[str] = []
    missing = 0
    unsupported = 0
    seen: set[str] = set()

    def consider(full: str, *, count_unsupported: bool) -> None:
        nonlocal unsupported
        key = os.path.normcase(full)
        if key in seen:
            return
        seen.add(key)
        if is_allowed(full, settings):
            natives.append(full)
        elif is_convertible(full):
            convertibles.append(full)
        elif count_unsupported:
            unsupported += 1

    for path in roots:
        if os.path.isdir(path):
            for full in _walk_folder_all(path, settings):
                consider(full, count_unsupported=False)
        elif os.path.isfile(path):
            consider(path, count_unsupported=True)
        else:
            missing += 1

    natives.sort(key=_natural_key)
    convertibles.sort(key=_natural_key)
    return natives, convertibles, missing, unsupported


def _walk_folder_all(folder: str, settings: dict) -> list[str]:
    """All candidate files in a folder (natives and convertibles), not yet filtered."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        if not settings.get("subfolders", True):
            dirnames[:] = []
        for name in filenames:
            if _is_skipped_name(name):
                continue
            full = os.path.join(dirpath, name)
            if is_allowed(full, settings) or is_convertible(full):
                found.append(full)
    found.sort(key=_natural_key)
    return found


def _walk_folder(folder: str, settings: dict) -> list[str]:
    return [path for path in _walk_folder_all(folder, settings) if is_allowed(path, settings)]


def _webview_choose(window, kind: str) -> list[str]:
    import webview

    if kind == "files":
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=WEBVIEW_TYPES,
        )
    elif kind == "open_preset":
        chosen = window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("JustPrint settings (*.jpset)", "All files (*.*)"),
        )
    elif kind == "save_preset":
        chosen = window.create_file_dialog(
            webview.FileDialog.SAVE,
            allow_multiple=False,
            file_types=("JustPrint settings (*.jpset)", "All files (*.*)"),
            save_filename="Print settings.jpset",
        )
    else:
        chosen = window.create_file_dialog(webview.FileDialog.FOLDER)
    if not chosen:
        return []
    if isinstance(chosen, str):
        return [chosen]
    return [path for path in chosen if path]


class DialogBridge:
    """Tk file dialogs, kept on their own thread so the window can stay responsive."""

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def ask(self, kind: str) -> list[str]:
        self._ensure()
        reply: queue.Queue = queue.Queue()
        self._queue.put((kind, reply))
        result = reply.get()
        if isinstance(result, Exception):
            raise result
        return result

    def _ensure(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._loop, name="justprint-dialogs", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        start = os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        while True:
            kind, reply = self._queue.get()
            try:
                root.attributes("-topmost", True)
                root.lift()
                if kind == "files":
                    chosen = filedialog.askopenfilenames(
                        parent=root,
                        title="Add files",
                        initialdir=start,
                        filetypes=FILETYPES,
                    )
                    paths = [path for path in chosen] if chosen else []
                elif kind == "open_preset":
                    chosen = filedialog.askopenfilename(
                        parent=root,
                        title="Load settings",
                        initialdir=start,
                        filetypes=(("JustPrint settings", "*.jpset"), ("All files", "*.*")),
                    )
                    paths = [chosen] if chosen else []
                elif kind == "save_preset":
                    chosen = filedialog.asksaveasfilename(
                        parent=root,
                        title="Save settings",
                        initialdir=start,
                        defaultextension=".jpset",
                        initialfile="Print settings.jpset",
                        filetypes=(("JustPrint settings", "*.jpset"), ("All files", "*.*")),
                    )
                    paths = [chosen] if chosen else []
                else:
                    chosen = filedialog.askdirectory(parent=root, title="Add folder", initialdir=start, mustexist=True)
                    paths = [chosen] if chosen else []
                reply.put(paths)
            except Exception as exc:
                reply.put(exc)
            finally:
                try:
                    root.attributes("-topmost", False)
                except Exception:
                    pass

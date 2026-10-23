"""Send page images to the Windows print spooler."""

from __future__ import annotations

import time

from justprint.papers import devmode_paper, match_win_paper

try:
    import win32con
    import win32gui
    import win32print
    import win32ui
    from PIL import ImageWin

    HAS_SPOOL = True
    SPOOL_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised only when pywin32 is missing
    win32con = None
    win32gui = None
    win32print = None
    win32ui = None
    ImageWin = None
    HAS_SPOOL = False
    SPOOL_ERROR = f"Windows printing support is missing ({exc})."


class SpoolError(Exception):
    """The printer rejected the job or could not be opened."""


# DMBIN_* common trays. "default" leaves the driver alone.
TRAY_IDS = {
    "auto": 7,  # DMBIN_AUTO
    "upper": 1,  # DMBIN_UPPER
    "lower": 2,  # DMBIN_LOWER
    "manual": 4,  # DMBIN_MANUAL
    "cassette": 14,  # DMBIN_CASSETTE
}
DMPAPER_USER = 256

# Extra wait after the Windows queue clears, before the paper is done.
# Zero sheets per minute means wait only until the queue is empty.
DEFAULT_SHEETS_PER_MINUTE = 6.0


def _devmode_int(devmode, name: str) -> int:
    try:
        return int(getattr(devmode, name) or 0)
    except Exception:
        return 0


def list_printers() -> list[str]:
    if not HAS_SPOOL:
        return []
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names: list[str] = []
    try:
        entries = win32print.EnumPrinters(flags)
    except Exception:
        return []
    for item in entries:
        name = item[2]
        if name and name not in names:
            names.append(name)
    return names


def default_printer() -> str:
    if not HAS_SPOOL:
        return ""
    try:
        return win32print.GetDefaultPrinter() or ""
    except Exception:
        return ""


def printer_defaults(name: str) -> dict:
    """Read paper/color/duplex/orientation defaults from the printer's DEVMODE."""
    empty = {"paper": None, "orientation": None, "color": None, "duplex": None, "copies": None}
    if not name or not HAS_SPOOL:
        return empty
    try:
        handle = win32print.OpenPrinter(name)
    except Exception:
        return empty
    try:
        info = win32print.GetPrinter(handle, 2)
        devmode = info.get("pDevMode")
        if devmode is None:
            return empty
        paper = match_win_paper(
            _devmode_int(devmode, "PaperSize"),
            _devmode_int(devmode, "PaperWidth"),
            _devmode_int(devmode, "PaperLength"),
        )
        orientation = {1: "portrait", 2: "landscape"}.get(int(getattr(devmode, "Orientation", 0) or 0))
        # DMCOLOR_MONOCHROME=1, DMCOLOR_COLOR=2
        color = {1: "grayscale", 2: "color"}.get(int(getattr(devmode, "Color", 0) or 0))
        duplex = {1: "simplex", 2: "long", 3: "short"}.get(int(getattr(devmode, "Duplex", 0) or 0))
        copies = int(getattr(devmode, "Copies", 0) or 0)
        return {
            "paper": paper,
            "orientation": orientation,
            "color": color,
            "duplex": duplex,
            "copies": copies if 1 <= copies <= 99 else None,
        }
    except Exception:
        return empty
    finally:
        try:
            win32print.ClosePrinter(handle)
        except Exception:
            pass


def printer_status(name: str) -> dict:
    if not name:
        return {"label": "No printer", "level": "warn"}
    if not HAS_SPOOL:
        return {"label": "Unavailable", "level": "error"}
    try:
        handle = win32print.OpenPrinter(name)
    except Exception:
        return {"label": "Unavailable", "level": "error"}
    try:
        info = win32print.GetPrinter(handle, 2)
        label, level = describe_status(int(info.get("Status") or 0), int(info.get("Attributes") or 0))
        return {"label": label, "level": level}
    except Exception:
        return {"label": "Unavailable", "level": "error"}
    finally:
        try:
            win32print.ClosePrinter(handle)
        except Exception:
            pass


def describe_status(status: int, attributes: int) -> tuple[str, str]:
    # PRINTER_ATTRIBUTE_WORK_OFFLINE
    if attributes & 0x00000400 and status == 0:
        return "Offline", "error"
    checks = (
        (0x00000008, "Paper jam", "error"),
        (0x00000010, "Paper out", "error"),
        (0x00000040, "Paper problem", "error"),
        (0x00400000, "Door open", "error"),
        (0x00040000, "No toner", "error"),
        (0x00200000, "Out of memory", "error"),
        (0x00000080, "Offline", "error"),
        (0x00001000, "Not available", "error"),
        (0x00000002, "Error", "error"),
        (0x00020000, "Toner low", "warn"),
        (0x00000001, "Paused", "warn"),
        (0x00000400, "Printing", "busy"),
        (0x00000200, "Busy", "busy"),
        (0x00004000, "Processing", "busy"),
        (0x00010000, "Warming up", "busy"),
        (0x00008000, "Initializing", "busy"),
        (0x00002000, "Waiting", "busy"),
    )
    for flag, label, level in checks:
        if status & flag:
            return label, level
    return "Ready", "ok"


def make_sink(printer_name: str, settings: dict, delay: float, stop_event):
    if settings.get("practice_run"):
        return PracticeSink(delay, stop_event)
    if not printer_name:
        raise SpoolError("Choose a printer first")
    if not HAS_SPOOL:
        raise SpoolError(SPOOL_ERROR or "Windows printing support is missing")
    return WindowsSink(printer_name, stop_event)


# JOB_STATUS_*
_JOB_PAUSED = 0x00000001
_JOB_ERROR = 0x00000002
_JOB_DELETING = 0x00000004
_JOB_SPOOLING = 0x00000008
_JOB_PRINTING = 0x00000010
_JOB_OFFLINE = 0x00000020
_JOB_PAPEROUT = 0x00000040
_JOB_PRINTED = 0x00000080
_JOB_DELETED = 0x00000100
_JOB_BLOCKED = 0x00000200
_JOB_USER_INTERVENTION = 0x00000400
_JOB_COMPLETE = 0x00001000
_JOB_DONE = _JOB_PRINTED | _JOB_COMPLETE | _JOB_DELETED | _JOB_DELETING


def fit_rect(src_w: int, src_h: int, dst_w: int, dst_h: int) -> tuple[int, int, int, int]:
    return layout_rect(src_w, src_h, dst_w, dst_h, {"scale": "fit", "horizontal_align": "center", "vertical_align": "middle"})


def layout_rect(src_w: int, src_h: int, dst_w: int, dst_h: int, settings: dict | None = None) -> tuple[int, int, int, int]:
    """Place content in the printable area using scale, alignment, margins, and offset."""
    settings = settings or {}
    # Margins/offsets are millimeters; approximate at 96 dpi device space when unknown.
    # Callers pass already-margin-shrunk dst_* when possible; we still apply mm→px via ratio to page.
    margin_l = float(settings.get("margin_left") or 0)
    margin_t = float(settings.get("margin_top") or 0)
    margin_r = float(settings.get("margin_right") or 0)
    margin_b = float(settings.get("margin_bottom") or 0)
    # Convert mm to pixels assuming dst is physical printable width (~letter 8.5in).
    px_per_mm = max(dst_w, 1) / 215.9
    left = int(margin_l * px_per_mm)
    top = int(margin_t * px_per_mm)
    right = int(margin_r * px_per_mm)
    bottom = int(margin_b * px_per_mm)
    area_w = max(1, dst_w - left - right)
    area_h = max(1, dst_h - top - bottom)
    scale_mode = str(settings.get("scale") or "fit").lower()
    if scale_mode == "actual":
        draw_w, draw_h = src_w, src_h
    elif scale_mode == "fill":
        scale = max(area_w / max(src_w, 1), area_h / max(src_h, 1))
        draw_w = max(1, int(src_w * scale))
        draw_h = max(1, int(src_h * scale))
    elif scale_mode == "percent":
        pct = max(1, int(settings.get("scale_percent") or 100)) / 100.0
        fit = min(area_w / max(src_w, 1), area_h / max(src_h, 1))
        draw_w = max(1, int(src_w * fit * pct))
        draw_h = max(1, int(src_h * fit * pct))
    else:
        scale = min(area_w / max(src_w, 1), area_h / max(src_h, 1))
        draw_w = max(1, int(src_w * scale))
        draw_h = max(1, int(src_h * scale))
    hx = str(settings.get("horizontal_align") or "center").lower()
    vy = str(settings.get("vertical_align") or "middle").lower()
    if hx == "left":
        x = left
    elif hx == "right":
        x = left + area_w - draw_w
    else:
        x = left + (area_w - draw_w) // 2
    if vy == "top":
        y = top
    elif vy == "bottom":
        y = top + area_h - draw_h
    else:
        y = top + (area_h - draw_h) // 2
    ox = int(float(settings.get("offset_x") or 0) * px_per_mm)
    oy = int(float(settings.get("offset_y") or 0) * px_per_mm)
    x += ox
    y += oy
    return (x, y, x + draw_w, y + draw_h)


class PracticeSink:
    """Exercises the queue without calling the spooler."""

    def __init__(self, delay: float, stop_event):
        self.delay = max(0.0, delay)
        self.stop_event = stop_event
        self.open = False
        self.pages = 0

    def begin_document(self, job_name: str, orientation: str, settings: dict) -> None:
        self.open = True

    def draw(self, image, orientation: str) -> bool:
        if not self.open:
            raise SpoolError("The print job is not open")
        if image.width < 1 or image.height < 1:
            raise SpoolError("Empty page")
        if self.stop_event.is_set():
            return False
        waited = 0.0
        while waited < self.delay:
            if self.stop_event.is_set():
                return False
            step = min(0.05, self.delay - waited)
            time.sleep(step)
            waited += step
        self.pages += 1
        return True

    def end_document(self) -> None:
        self.open = False

    def wait_for_job(self, on_status=None, expected_pages: int = 0, sheets_per_minute: float = DEFAULT_SHEETS_PER_MINUTE) -> bool:
        # Practice runs stay fast unless JUSTPRINT_PRACTICE_DELAY is set.
        _ = sheets_per_minute
        total = max(1, int(expected_pages or self.pages or 1))
        step = self.delay if self.delay > 0 else 0.02
        for page in range(1, total + 1):
            if self.stop_event.is_set():
                return False
            if on_status is not None:
                on_status({"pagesPrinted": page, "totalPages": total, "label": "Printing"})
            waited = 0.0
            while waited < step:
                if self.stop_event.is_set():
                    return False
                slice_len = min(0.05, step - waited)
                time.sleep(slice_len)
                waited += slice_len
        return True

    def abort(self) -> None:
        self.open = False

    def close(self) -> None:
        self.open = False


class WindowsSink:
    """One spool document at a time. Copies are handled by the caller."""

    def __init__(self, printer_name: str, stop_event):
        self.printer_name = printer_name
        self.stop_event = stop_event
        self._handle = None
        self._control = None
        self._dc = None
        self._hdc = None
        self._devmode = None
        self._started = False
        self._orientation = "portrait"
        self._job_name = "JustPrint"
        self._settings: dict = {}
        self._job_id: int | None = None
        self._pending_job_id: int | None = None
        self._open_control()

    def begin_document(self, job_name: str, orientation: str, settings: dict) -> None:
        self._job_name = _clean_job_name(job_name)
        self._settings = settings
        self._orientation = orientation if orientation in {"portrait", "landscape"} else "portrait"
        self._job_id = None
        self._pending_job_id = None
        try:
            self._handle = win32print.OpenPrinter(self.printer_name)
            info = win32print.GetPrinter(self._handle, 2)
            devmode = info.get("pDevMode")
            if devmode is None:
                raise SpoolError("This printer did not provide paper settings")
            saved = _snapshot_devmode(devmode)
            _apply_devmode(devmode, settings, self._orientation)
            try:
                self._hdc = win32gui.CreateDC("WINSPOOL", self.printer_name, devmode)
            except Exception:
                _restore_devmode(devmode, saved)
                self._hdc = win32gui.CreateDC("WINSPOOL", self.printer_name, devmode)
            self._devmode = devmode
            self._dc = win32ui.CreateDCFromHandle(self._hdc)
            job_id = self._dc.StartDoc(self._job_name)
            try:
                job_id = int(job_id)
            except (TypeError, ValueError):
                job_id = 0
            self._job_id = job_id if job_id > 0 else None
            self._started = True
        except SpoolError:
            self._cleanup_doc(abort=True)
            raise
        except Exception as exc:
            self._cleanup_doc(abort=True)
            raise SpoolError(f"Could not start a print job ({exc})") from exc

    def draw(self, image, orientation: str) -> bool:
        if self._dc is None:
            raise SpoolError("The print job is not open")
        if orientation != self._orientation:
            self._switch_orientation(orientation)
        try:
            self._dc.StartPage()
            self._blit(image)
            self._dc.EndPage()
        except SpoolError:
            raise
        except Exception as exc:
            raise SpoolError(f"Could not draw a page ({exc})") from exc
        return True

    def end_document(self) -> None:
        job_id = self._job_id
        job_name = self._job_name
        try:
            if self._started and self._dc is not None:
                self._dc.EndDoc()
                self._started = False
        except Exception as exc:
            self._pending_job_id = None
            raise SpoolError(f"Could not finish the print job ({exc})") from exc
        finally:
            self._job_id = None
            self._cleanup_doc(abort=False)
        self._pending_job_id = self._resolve_job_id(job_id, job_name)

    def wait_for_job(self, on_status=None, expected_pages: int = 0, sheets_per_minute: float = DEFAULT_SHEETS_PER_MINUTE) -> bool:
        """Wait until the printer finishes this file, not just spools it."""
        job_id = self._pending_job_id
        self._pending_job_id = None
        return wait_for_file_complete(
            self.printer_name,
            job_id,
            self.stop_event,
            on_status,
            job_name=self._job_name,
            expected_pages=expected_pages,
            control_handle=self._control,
            sheets_per_minute=sheets_per_minute,
        )

    def abort(self) -> None:
        pending = self._pending_job_id
        self._pending_job_id = None
        self._cleanup_doc(abort=True)
        if pending and self._control is not None:
            _cancel_spool_job(self._control, pending)

    def close(self) -> None:
        pending = self._pending_job_id
        self._pending_job_id = None
        self._cleanup_doc(abort=True)
        if pending and self._control is not None:
            _cancel_spool_job(self._control, pending)
        if self._control is not None:
            try:
                win32print.ClosePrinter(self._control)
            except Exception:
                pass
            self._control = None

    def _switch_orientation(self, orientation: str) -> None:
        if self._devmode is None:
            self._orientation = orientation
            return
        self._devmode.Orientation = _win_orientation(orientation)
        self._devmode.Fields |= win32con.DM_ORIENTATION
        try:
            win32gui.ResetDC(self._hdc, self._devmode)
            self._orientation = orientation
            return
        except Exception:
            pass
        name = self._job_name
        settings = self._settings
        self.end_document()
        if not self.wait_for_job():
            raise SpoolError("Stopped before the page finished")
        self.begin_document(name, orientation, settings)

    def _blit(self, image) -> None:
        horz = int(self._dc.GetDeviceCaps(win32con.HORZRES) or 0)
        vert = int(self._dc.GetDeviceCaps(win32con.VERTRES) or 0)
        if horz <= 0 or vert <= 0:
            raise SpoolError("The printer reported an empty page")
        rect = layout_rect(image.width, image.height, horz, vert, self._settings or {})
        dib = ImageWin.Dib(image.convert("RGB"))
        dib.draw(self._dc.GetHandleOutput(), rect)

    def _open_control(self) -> None:
        all_access = getattr(win32print, "PRINTER_ALL_ACCESS", 0)
        access_options = (
            all_access,
            win32print.PRINTER_ACCESS_ADMINISTER | win32print.PRINTER_ACCESS_USE,
            win32print.PRINTER_ACCESS_USE,
        )
        last_error: Exception | None = None
        for access in access_options:
            if not access:
                continue
            try:
                self._control = win32print.OpenPrinter(self.printer_name, {"DesiredAccess": access})
                return
            except Exception as exc:
                last_error = exc
                self._control = None
        try:
            self._control = win32print.OpenPrinter(self.printer_name)
        except Exception as exc:
            raise SpoolError(f"Could not open the printer ({exc})") from (last_error or exc)

    def _resolve_job_id(self, preferred: int | None, job_name: str) -> int | None:
        handle = self._control
        if handle is None:
            return preferred
        try:
            jobs = list(win32print.EnumJobs(handle, 0, 512, 1) or [])
        except Exception:
            return preferred
        if preferred:
            for job in jobs:
                if int(job.get("JobId") or 0) == preferred:
                    return preferred
        matches = [job for job in jobs if str(job.get("pDocument") or "") == job_name]
        if not matches:
            return preferred
        matches.sort(key=lambda job: int(job.get("JobId") or 0), reverse=True)
        return int(matches[0].get("JobId") or 0) or preferred

    def _cleanup_doc(self, abort: bool) -> None:
        if abort and self._started and self._dc is not None:
            try:
                self._dc.AbortDoc()
            except Exception:
                pass
        self._started = False
        if self._dc is not None:
            try:
                self._dc.DeleteDC()
            except Exception:
                pass
        elif self._hdc is not None:
            try:
                win32gui.DeleteDC(self._hdc)
            except Exception:
                pass
        self._dc = None
        self._hdc = None
        self._devmode = None
        if self._handle is not None:
            try:
                win32print.ClosePrinter(self._handle)
            except Exception:
                pass
            self._handle = None


def _printer_name_from_handle(handle) -> str | None:
    try:
        info = win32print.GetPrinter(handle, 2)
        return info.get("pPrinterName") or info.get("PrinterName")
    except Exception:
        return None


def _printer_status_busy(status: int) -> bool:
    return bool(
        status
        & (
            0x00000200  # busy
            | 0x00000400  # printing
            | 0x00004000  # processing
            | 0x00010000  # warming up
            | 0x00002000  # waiting
            | 0x00008000  # initializing
        )
    )


def _jobs_for_name(jobs: list, job_name: str | None) -> list:
    if not job_name:
        return list(jobs or [])
    name = str(job_name)
    return [job for job in jobs or [] if str(job.get("pDocument") or "") == name]


def wait_for_file_complete(
    printer_name: str,
    job_id: int | None,
    stop_event,
    on_status=None,
    *,
    job_name: str = "",
    expected_pages: int = 0,
    control_handle=None,
    sheets_per_minute: float = DEFAULT_SHEETS_PER_MINUTE,
) -> bool:
    """Wait until one file has finished printing before the next file starts.

    1. Wait until this job leaves the Windows print queue (or was never seen).
    2. Then keep waiting for an estimated print duration based on page count and
       sheets-per-minute. Windows PagePrinted counts are not trusted alone.
    """
    if not HAS_SPOOL or not printer_name:
        return not stop_event.is_set()

    expected = max(1, int(expected_pages or 1))
    ppm = float(sheets_per_minute or 0.0)
    # Zero means wait only until the Windows queue is empty.
    if ppm <= 0:
        estimate_seconds = 0.0
    else:
        estimate_seconds = max(8.0, (expected / ppm) * 60.0)
        estimate_seconds = min(estimate_seconds, 3600.0)

    started_at = time.time()
    left_queue_at: float | None = None
    peak_pages = 0
    saw_job = False

    def publish(pages: int, total: int, label: str) -> None:
        if on_status is None:
            return
        on_status({"pagesPrinted": pages, "totalPages": total, "label": label})

    def estimated_pages(now: float) -> int:
        elapsed = max(0.0, now - started_at)
        done = int(elapsed / estimate_seconds * expected) if estimate_seconds else expected
        return max(0, min(expected, done))

    handle = control_handle
    owns = False
    if handle is None:
        try:
            handle = win32print.OpenPrinter(printer_name)
            owns = True
        except Exception as exc:
            raise SpoolError(f"Could not watch the print job ({exc})") from exc

    try:
        while True:
            if stop_event.is_set():
                if job_id:
                    _cancel_spool_job(handle, job_id)
                return False

            job = _find_spool_job(handle, job_id) if job_id else None
            if job is None and job_name:
                matches = _jobs_for_name(list(win32print.EnumJobs(handle, 0, 512, 1) or []), job_name)
                if matches:
                    job = max(matches, key=lambda item: int(item.get("JobId") or 0))

            now = time.time()
            printer_status = 0
            try:
                printer_status = int(win32print.GetPrinter(handle, 2).get("Status") or 0)
            except Exception:
                pass
            busy = _printer_status_busy(printer_status)

            if job is not None:
                saw_job = True
                left_queue_at = None
                status = int(job.get("Status") or 0)
                pages = max(int(job.get("PagesPrinted") or 0), estimated_pages(now))
                peak_pages = max(peak_pages, pages)
                publish(min(pages, expected), expected, _job_progress(job, status)["label"])
            else:
                if saw_job and left_queue_at is None:
                    left_queue_at = now
                elif not saw_job and left_queue_at is None and (now - started_at) >= 2.0:
                    # Job never appeared (common on fast network printers).
                    left_queue_at = now
                pages = max(peak_pages, estimated_pages(now))
                peak_pages = max(peak_pages, pages)
                publish(min(pages, expected), expected, "Printing" if (busy or left_queue_at is None) else "Printing")

            if left_queue_at is not None and not busy:
                # After the Windows queue is clear: either finish immediately (ppm=0)
                # or wait out the estimated print time.
                ready = estimate_seconds <= 0 or (now - started_at) >= estimate_seconds
                if ready:
                    quiet_until = now + (0.4 if estimate_seconds <= 0 else 1.5)
                    while time.time() < quiet_until:
                        if stop_event.is_set():
                            return False
                        try:
                            status_now = int(win32print.GetPrinter(handle, 2).get("Status") or 0)
                        except Exception:
                            status_now = 0
                        if _printer_status_busy(status_now):
                            break
                        if stop_event.wait(0.25):
                            return False
                    else:
                        publish(expected, expected, "Printing")
                        return True

            if stop_event.wait(0.4):
                if job_id:
                    _cancel_spool_job(handle, job_id)
                return False
    finally:
        if owns and handle is not None:
            try:
                win32print.ClosePrinter(handle)
            except Exception:
                pass


def _find_spool_job(handle, job_id: int):
    try:
        jobs = win32print.EnumJobs(handle, 0, 512, 1)
    except Exception:
        return None
    for job in jobs or []:
        if int(job.get("JobId") or 0) == job_id:
            return job
    return None


def _cancel_spool_job(handle, job_id: int) -> None:
    try:
        win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_CANCEL)
    except Exception:
        try:
            win32print.SetJob(handle, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
        except Exception:
            pass


def _job_progress(job: dict, status: int) -> dict:
    pages = int(job.get("PagesPrinted") or 0)
    total = int(job.get("TotalPages") or 0)
    if status & _JOB_PAPEROUT:
        label = "Paper out"
    elif status & _JOB_OFFLINE:
        label = "Printer offline"
    elif status & _JOB_USER_INTERVENTION:
        label = "Printer needs attention"
    elif status & _JOB_ERROR:
        label = "Printer error"
    elif status & _JOB_PAUSED or status & _JOB_BLOCKED:
        label = "Printing"
    elif status & _JOB_PRINTING:
        label = "Printing"
    elif status & _JOB_SPOOLING:
        label = "Sending"
    else:
        label = "Waiting for the printer"
    return {"pagesPrinted": pages, "totalPages": total, "label": label}


def _win_orientation(name: str) -> int:
    if name == "landscape":
        return win32con.DMORIENT_LANDSCAPE
    return win32con.DMORIENT_PORTRAIT


def _apply_devmode(devmode, settings: dict, orientation: str) -> None:
    paper = str(settings.get("paper") or "default").lower()
    tray = str(settings.get("paper_tray") or "default").lower()
    custom_w = float(settings.get("custom_paper_width") or 0)
    custom_h = float(settings.get("custom_paper_height") or 0)
    color = win32con.DMCOLOR_MONOCHROME if settings.get("color") == "grayscale" else win32con.DMCOLOR_COLOR
    duplex = {"simplex": win32con.DMDUP_SIMPLEX, "long": win32con.DMDUP_VERTICAL, "short": win32con.DMDUP_HORIZONTAL}
    if custom_w >= 20 and custom_h >= 20:
        # DEVMODE PaperWidth/Length are tenths of a millimeter.
        _try_set(devmode, "PaperSize", DMPAPER_USER, win32con.DM_PAPERSIZE)
        _try_set(devmode, "PaperWidth", int(round(custom_w * 10)), win32con.DM_PAPERWIDTH)
        _try_set(devmode, "PaperLength", int(round(custom_h * 10)), win32con.DM_PAPERLENGTH)
    elif paper != "default":
        spec = devmode_paper(paper)
        if spec is not None:
            form_flag = getattr(win32con, "DM_FORMNAME", 0x10000)
            _try_set(devmode, "PaperSize", spec["size"], win32con.DM_PAPERSIZE)
            if spec["form"]:
                _try_set(devmode, "FormName", spec["form"], form_flag)
            if spec["custom"]:
                _try_set(devmode, "PaperWidth", spec["width"], getattr(win32con, "DM_PAPERWIDTH", 0x8))
                _try_set(devmode, "PaperLength", spec["length"], getattr(win32con, "DM_PAPERLENGTH", 0x4))
    if tray != "default" and tray in TRAY_IDS:
        _try_set(devmode, "DefaultSource", TRAY_IDS[tray], win32con.DM_DEFAULTSOURCE)
    _try_set(devmode, "Orientation", _win_orientation(orientation), win32con.DM_ORIENTATION)
    _try_set(devmode, "Copies", 1, win32con.DM_COPIES)
    _try_set(devmode, "Color", color, win32con.DM_COLOR)
    _try_set(devmode, "Duplex", duplex.get(settings.get("duplex", "simplex"), win32con.DMDUP_SIMPLEX), win32con.DM_DUPLEX)


def _try_set(devmode, name: str, value, field_flag: int) -> None:
    try:
        setattr(devmode, name, value)
        devmode.Fields |= field_flag
    except Exception:
        return


def _snapshot_devmode(devmode) -> dict:
    return {
        "PaperSize": devmode.PaperSize,
        "PaperWidth": getattr(devmode, "PaperWidth", 0),
        "PaperLength": getattr(devmode, "PaperLength", 0),
        "FormName": devmode.FormName,
        "Orientation": devmode.Orientation,
        "Copies": devmode.Copies,
        "Color": devmode.Color,
        "Duplex": devmode.Duplex,
        "Fields": devmode.Fields,
    }


def _restore_devmode(devmode, saved: dict) -> None:
    for key, value in saved.items():
        setattr(devmode, key, value)


def _clean_job_name(name: str) -> str:
    cleaned = "".join(ch if ch.isprintable() else " " for ch in (name or ""))
    cleaned = " ".join(cleaned.split())
    return (cleaned or "JustPrint")[:120]

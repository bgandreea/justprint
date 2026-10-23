"""Launch JustPrint."""

from __future__ import annotations

import atexit
import argparse
import ctypes
import socket
import sys
import threading
import time
import webbrowser

from justprint.app import App
from justprint.paths import app_root
from justprint.server import serve


def main() -> None:
    if sys.platform != "win32":
        print("JustPrint sends jobs through the Windows print spooler, so it needs Windows.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Print a queue of files and folders.")
    parser.add_argument("paths", nargs="*", help="Files or folders to add when the window opens")
    parser.add_argument("--browser", action="store_true", help="Open in the browser instead of a desktop window")
    args = parser.parse_args()

    app = App()

    def _clear_list_on_exit() -> None:
        try:
            app.discard_list()
        except Exception:
            pass

    atexit.register(_clear_list_on_exit)
    if args.paths:
        app.add_paths(args.paths)
    httpd = serve(app)
    _wait_until_listening(httpd)
    host, port = httpd.server_address
    url = f"http://{host}:{port}/"
    print(f"JustPrint is running at {url}")
    open_window(app, url, force_browser=args.browser)


def open_window(app: App, url: str, force_browser: bool = False) -> None:
    if not force_browser:
        try:
            import webview

            loaded = threading.Event()
            settings = app._settings_copy()
            width = int(settings.get("window_width") or 1540)
            height = int(settings.get("window_height") or 860)
            width = min(WINDOW_MAX_WIDTH, max(WINDOW_MIN_WIDTH, width))
            chrome = WindowChrome()
            window = webview.create_window(
                "JustPrint - A batch printing tool",
                url,
                width=width,
                height=max(WINDOW_MIN_HEIGHT, height),
                min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
                background_color="#f3f5f8",
                text_select=True,
                easy_drag=False,
                frameless=True,
                hidden=True,
                js_api=chrome,
            )
            app.window = window
            chrome._window = window
            window.events.loaded += lambda: loaded.set()
            window.events.loaded += lambda: window.set_title("JustPrint - A batch printing tool")
            window.events.loaded += lambda: install_file_drop(window, app)
            window.events.loaded += lambda: reveal_window(window)
            window.events.maximized += lambda: sync_maximized(window, True)
            window.events.restored += lambda: sync_maximized(window, False)
            window.events.resized += lambda w, h: save_window_size(app, w, h)
            started = time.time()
            icon = app_root() / "justprint.ico"
            webview.start(icon=str(icon) if icon.is_file() else None)
            # A normal close happens after the page has loaded. A failed window returns immediately.
            if loaded.is_set() or time.time() - started > 3:
                return
            print("The desktop window did not open. Opening a browser instead.")
        except Exception as exc:
            print(f"Desktop window unavailable ({exc}). Opening a browser instead.")
    webbrowser.open(url)
    # Windowed builds have no console for input(); keep the process alive instead.
    if getattr(sys, "frozen", False):
        while True:
            time.sleep(1)
    print("Press Enter to stop JustPrint.")
    try:
        input()
    except EOFError:
        while True:
            time.sleep(1)


_last_saved_size = (0, 0)
_size_lock = threading.Lock()
WINDOW_MIN_WIDTH = 1540
WINDOW_MIN_HEIGHT = 860
WINDOW_MAX_WIDTH = 1600


def limit_window_width(window) -> None:
    """Kept so older call sites stay harmless. Width is limited in the frame hook."""
    return


class WindowChrome:
    """Minimize, maximize, and close for the custom banner."""

    def __init__(self) -> None:
        self._window = None

    def minimize_window(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def toggle_maximize(self) -> bool:
        return toggle_window_zoom(self._window)

    def close_window(self) -> None:
        if self._window is not None:
            self._window.destroy()

    def nudge_window(self, dx: int, dy: int) -> None:
        """Move by a physical-pixel delta. The page drag uses this directly."""
        if self._window is None:
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
        user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        user32.GetDpiForWindow.restype = ctypes.c_uint
        user32.IsZoomed.argtypes = [ctypes.c_void_p]
        user32.IsZoomed.restype = ctypes.c_int
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.c_int
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        hwnd = int(self._window.native.Handle.ToInt64())
        try:
            dx = int(dx)
            dy = int(dy)
        except (TypeError, ValueError):
            return
        if dx == 0 and dy == 0:
            return
        # A double-click can report a bogus jump. That throws the window off-screen.
        if abs(dx) > 250 or abs(dy) > 250:
            return
        if user32.IsZoomed(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE, before the move
            sync_maximized(self._window, False)
        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return
        if rect.left < -10000 or rect.top < -10000:
            return
        scale = (user32.GetDpiForWindow(hwnd) or 96) / 96
        user32.SetWindowPos(
            hwnd,
            None,
            rect.left + int(round(float(dx) * scale)),
            rect.top + int(round(float(dy) * scale)),
            0,
            0,
            0x0001 | 0x0004 | 0x0010,
        )


def remember_work_area(window) -> None:
    """Kept for older call sites. MaximizedBounds makes Win+Up toggle instead of staying maximized."""
    return


def toggle_window_zoom(window) -> bool:
    """Maximize or restore without letting a borderless window leave the screen."""
    if window is None:
        return False
    try:
        hwnd = int(window.native.Handle.ToInt64())
    except Exception:
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsZoomed.argtypes = [ctypes.c_void_p]
    user32.IsZoomed.restype = ctypes.c_int
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.IsIconic.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_int
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)
        sync_maximized(window, False)
        return False
    remember_work_area(window)
    user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    snap_to_work_area(window)
    sync_maximized(window, True)
    return True


def snap_to_work_area(window) -> None:
    """The maximized client is cropped in WM_NCCALCSIZE. Moving it here breaks Win+Up."""
    return


def reveal_window(window) -> None:
    """Show the window first. The frame is applied afterward on the UI thread."""
    try:
        window.show()
    except Exception:
        try:
            window.native.Show()
        except Exception:
            pass

    def finish() -> None:
        try:
            install_window_frame(window)
        except Exception:
            pass

    try:
        from System import Action

        window.native.BeginInvoke(Action(finish))
    except Exception:
        pass


def sync_maximized(window, maximized: bool) -> None:
    try:
        window.evaluate_js(
            "document.querySelector('.app-banner')?.classList.toggle('is-maximized', "
            + ("true" if maximized else "false")
            + ")"
        )
    except Exception:
        pass


_frame_callbacks: list[object] = []
_framed_hwnds: set[int] = set()
_enforcing_frame = False


def _chrome_style(style: int) -> int:
    """A real caption, with the bar itself removed in WM_NCCALCSIZE.

    Win+arrow snap uses the caption to decide maximize and restore. Stripping it
    makes a second Win+Up throw the window off the screen. The blue banner is
    still the visible title bar.
    """
    # Drop WS_POPUP. Keep WS_OVERLAPPEDWINDOW (caption, resize, min, max, menu).
    return (style & ~0x80000000) | 0x00CF0000


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


class _WINDOWPOS(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("hwndInsertAfter", ctypes.c_void_p),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("cx", ctypes.c_int),
        ("cy", ctypes.c_int),
        ("flags", ctypes.c_uint),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


def keep_frameless(window) -> None:
    """A resize can put the native caption back. Strip it and keep the resize border."""
    global _enforcing_frame
    if _enforcing_frame:
        return
    _enforcing_frame = True
    try:
        hwnd = int(window.native.Handle.ToInt64())
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        style = user32.GetWindowLongPtrW(hwnd, -16)
        desired = _chrome_style(style)
        if desired == style:
            return
        user32.SetWindowLongPtrW(hwnd, -16, desired)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception:
        pass
    finally:
        _enforcing_frame = False


_pending_tile = None


def _tile_kind(x: int, y: int, cx: int, cy: int, work) -> bool:
    """True when the rect is a half or quarter snap on this work area."""
    width = work.right - work.left
    height = work.bottom - work.top
    if cx < width * 0.2 or cy < height * 0.2:
        return False
    on_left = abs(x - work.left) <= 16
    on_right = abs((x + cx) - work.right) <= 20
    on_top = y <= work.top + 12
    on_bottom = abs((y + cy) - work.bottom) <= 24
    full_w = cx >= width - 40
    full_h = cy >= height - 40
    short = height * 0.25 < cy < height - 40
    narrow = cx < width - 40
    if full_w and short and (on_top or on_bottom):
        return True
    if full_h and narrow and (on_left or on_right):
        return True
    if short and narrow and (on_top or on_bottom) and (on_left or on_right):
        return True
    return False


def _keep_tile(user32, hwnd, lparam) -> None:
    """WinForms puts the restored rectangle back after a snap from the maximized window.

    The snap itself is the right place. The follow-up restore is what makes the
    window jump away, so that one move is put back on the snap.
    """
    global _pending_tile
    pos = ctypes.cast(lparam, ctypes.POINTER(_WINDOWPOS))
    flags = int(pos.contents.flags)
    if flags & 0x0001 and flags & 0x0002:
        return
    x = int(pos.contents.x)
    y = int(pos.contents.y)
    cx = int(pos.contents.cx)
    cy = int(pos.contents.cy)
    if x <= -8000 or y <= -8000 or cx < 80 or cy < 60:
        _pending_tile = None
        return
    proposed = _RECT(x, y, x + cx, y + cy)
    monitor = user32.MonitorFromRect(ctypes.byref(proposed), 2)
    display = _MONITORINFO()
    display.cbSize = ctypes.sizeof(_MONITORINFO)
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(display)):
        return
    kind = _tile_kind(x, y, cx, cy, display.rcWork)
    if kind:
        _pending_tile = (x, y, cx, cy, int(ctypes.windll.kernel32.GetTickCount()))
        return
    pending = _pending_tile
    _pending_tile = None
    if pending is None:
        return
    age = int(ctypes.windll.kernel32.GetTickCount()) - pending[4]
    if age > 200:
        return
    # The next move in this same burst is WinForms putting the restored
    # rectangle back. Put the snap rectangle back instead.
    pos.contents.x = pending[0]
    pos.contents.y = pending[1]
    pos.contents.cx = pending[2]
    pos.contents.cy = pending[3]
    pos.contents.flags = flags & ~0x0001 & ~0x0002
    _pending_tile = pending


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", _RECT * 3), ("lppos", ctypes.POINTER(_WINDOWPOS))]


def install_window_frame(window) -> None:
    """Hide the native title bar and let the blue banner act as one.

    Resize borders and the 1600px drag limit stay. Maximize still fills the screen.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)

    subclass_proc = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_ssize_t,
        ctypes.c_ssize_t,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    )
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
    user32.GetDpiForWindow.restype = ctypes.c_uint
    user32.IsZoomed.argtypes = [ctypes.c_void_p]
    user32.IsZoomed.restype = ctypes.c_int
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(_RECT), ctypes.c_uint]
    user32.MonitorFromRect.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = ctypes.c_int
    user32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.POINTER(_POINT)]
    user32.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RECT)]
    comctl32.SetWindowSubclass.argtypes = [
        ctypes.c_void_p,
        subclass_proc,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    comctl32.SetWindowSubclass.restype = ctypes.c_int
    comctl32.DefSubclassProc.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_ssize_t,
        ctypes.c_ssize_t,
    ]
    comctl32.DefSubclassProc.restype = ctypes.c_ssize_t

    dwmapi.DwmExtendFrameIntoClientArea.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    dwmapi.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]

    class _MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    hwnd = int(window.native.Handle.ToInt64())
    if hwnd in _framed_hwnds:
        style = user32.GetWindowLongPtrW(hwnd, -16)
        desired = _chrome_style(style)
        if desired != style:
            user32.SetWindowLongPtrW(hwnd, -16, desired)
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0020 | 0x0010)
        remember_work_area(window)
        return

    def handle(hwnd, msg, wparam, lparam, default):
        if msg == 0x0083:  # WM_NCCALCSIZE
            style = user32.GetWindowLongPtrW(hwnd, -16)
            desired = _chrome_style(style)
            if desired != style:
                user32.SetWindowLongPtrW(hwnd, -16, desired)
            # DefWindowProc has to see this message. Skipping it makes Win+arrow
            # from a maximized window restore instead of tiling.
            if not wparam:
                return default()
            params = ctypes.cast(lparam, ctypes.POINTER(_NCCALCSIZE_PARAMS))
            suggested = params.contents.rgrc[0]
            suggested_rect = _RECT(suggested.left, suggested.top, suggested.right, suggested.bottom)
            default()
            slot = params.contents.rgrc[0]
            slot.left = suggested_rect.left
            slot.top = suggested_rect.top
            slot.right = suggested_rect.right
            slot.bottom = suggested_rect.bottom
            monitor = user32.MonitorFromRect(ctypes.byref(suggested_rect), 2)
            display = _MONITORINFO()
            display.cbSize = ctypes.sizeof(_MONITORINFO)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(display)):
                work = display.rcWork
                covers = (
                    suggested_rect.left <= work.left
                    and suggested_rect.top <= work.top
                    and suggested_rect.right >= work.right
                    and suggested_rect.bottom >= work.bottom - 2
                )
                if covers or user32.IsZoomed(hwnd):
                    slot.left = work.left
                    slot.top = work.top
                    slot.right = work.right
                    slot.bottom = work.bottom
            params.contents.rgrc[0] = slot
            return 0
        if msg == 0x0024:  # WM_GETMINMAXINFO
            result = default()
            info = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO))
            dpi = user32.GetDpiForWindow(hwnd) or 96
            scale = dpi / 96
            # Half and quarter snaps are smaller than the layout. A large minimum
            # makes Windows abandon the snap and restore the window, which is the
            # jump off the maximized size. The layout size is applied afterwards.
            min_track = info.contents.ptMinTrackSize
            min_track.x = int(320 * scale)
            min_track.y = int(240 * scale)
            info.contents.ptMinTrackSize = min_track
            # Leave ptMaxSize and ptMaxPosition alone. Changing them makes a second
            # Win+Up restore the window. The client is cropped to the work area in
            # WM_NCCALCSIZE, so the taskbar stays visible. The drag limit must not
            # clamp that maximized size.
            monitor = user32.MonitorFromWindow(hwnd, 2)
            display = _MONITORINFO()
            display.cbSize = ctypes.sizeof(_MONITORINFO)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(display)):
                work = display.rcWork
                max_track = info.contents.ptMaxTrackSize
                full_w = work.right - work.left
                full_h = work.bottom - work.top
                if max_track.x < full_w:
                    max_track.x = full_w
                if max_track.y < full_h:
                    max_track.y = full_h
                info.contents.ptMaxTrackSize = max_track
            return result
        if msg == 0x0214:  # WM_SIZING: drag limit only, maximize is not affected
            rect_ptr = ctypes.cast(lparam, ctypes.POINTER(_RECT))
            rect = rect_ptr.contents
            dpi = user32.GetDpiForWindow(hwnd) or 96
            scale = dpi / 96
            max_w = int(WINDOW_MAX_WIDTH * scale)
            min_w = int(WINDOW_MIN_WIDTH * scale)
            min_h = int(WINDOW_MIN_HEIGHT * scale)
            if rect.right - rect.left > max_w:
                if wparam in (1, 4, 7):
                    rect.left = rect.right - max_w
                else:
                    rect.right = rect.left + max_w
            if rect.right - rect.left < min_w:
                if wparam in (1, 4, 7):
                    rect.left = rect.right - min_w
                else:
                    rect.right = rect.left + min_w
            if rect.bottom - rect.top < min_h:
                if wparam in (3, 4, 5):
                    rect.top = rect.bottom - min_h
                else:
                    rect.bottom = rect.top + min_h
            rect_ptr.contents = rect
            return 1
        if msg == 0x0046:  # WM_WINDOWPOSCHANGING
            _keep_tile(user32, hwnd, lparam)
        if msg == 0x0084:  # WM_NCHITTEST
            return _caption_hit(user32, hwnd, lparam)
        if msg == 0x00A3 and wparam in (2, 12):  # double-click caption or top edge
            # The default handler snaps or hides a borderless window. Maximize instead.
            toggle_window_zoom(window)
            return 0
        return default()

    def proc(hwnd, msg, wparam, lparam, uid, data):
        return handle(
            hwnd,
            msg,
            wparam,
            lparam,
            lambda: comctl32.DefSubclassProc(hwnd, msg, wparam, lparam),
        )

    callback = subclass_proc(proc)
    _frame_callbacks.append(callback)
    subclassed = False
    try:
        subclassed = bool(comctl32.SetWindowSubclass(hwnd, callback, 1, 0))
    except Exception:
        subclassed = False
    if not subclassed:
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_ssize_t,
            ctypes.c_ssize_t,
        )
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_ssize_t,
            ctypes.c_ssize_t,
        ]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        previous = user32.GetWindowLongPtrW(hwnd, -4)

        def wndproc(hwnd, msg, wparam, lparam):
            return handle(
                hwnd,
                msg,
                wparam,
                lparam,
                lambda: user32.CallWindowProcW(previous, hwnd, msg, wparam, lparam),
            )

        fallback = wndproc_type(wndproc)
        _frame_callbacks.append(fallback)
        user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(fallback, ctypes.c_void_p).value)

    _framed_hwnds.add(hwnd)
    style = _chrome_style(user32.GetWindowLongPtrW(hwnd, -16))
    user32.SetWindowLongPtrW(hwnd, -16, style)

    remember_work_area(window)
    # The form minimum is the layout size, which is taller than a top-half snap
    # and wider than a side snap. Windows then cancels the snap and jumps back
    # to the restored window. Dragging still stops at the layout size.
    try:
        from System.Drawing import Size

        window.native.MinimumSize = Size(320, 240)
    except Exception:
        pass
    margins = _MARGINS(1, 1, 1, 1)
    dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    preference = ctypes.c_int(2)  # DWMWCP_ROUND
    dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference))
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0004 | 0x0020 | 0x0010)


def _caption_hit(user32, hwnd, lparam) -> int:
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    point = _POINT(x, y)
    user32.ScreenToClient(hwnd, ctypes.byref(point))
    rect = _RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    width = rect.right
    height = rect.bottom
    if width <= 0 or height <= 0:
        return 1
    dpi = user32.GetDpiForWindow(hwnd) or 96
    scale = dpi / 96
    border = max(6, int(round(6 * scale)))
    button = int(round(46 * scale))
    banner = int(round(56 * scale))
    zoomed = bool(user32.IsZoomed(hwnd))
    cx, cy = point.x, point.y
    on_buttons = 0 <= cy < banner and cx >= width - 3 * button
    in_banner = 0 <= cy < banner and not on_buttons
    if not zoomed and not on_buttons:
        left = cx < border
        right = cx >= width - border
        # The title bar is not a top resize edge. That double-click snaps the
        # window upward instead of maximizing it.
        top = cy < border and not in_banner
        bottom = cy >= height - border
        if top and left:
            return 13
        if top and right:
            return 14
        if bottom and left:
            return 16
        if bottom and right:
            return 17
        if left:
            return 10
        if right:
            return 11
        if top:
            return 12
        if bottom:
            return 15
    if in_banner:
        return 1
    return 1


def save_window_size(app: App, width: int, height: int) -> None:
    global _last_saved_size
    try:
        hwnd = int(app.window.native.Handle.ToInt64())
        if ctypes.windll.user32.IsZoomed(hwnd):
            return
    except Exception:
        pass
    size = (min(WINDOW_MAX_WIDTH, int(width)), int(height))
    with _size_lock:
        if size == _last_saved_size or size[0] < 640 or size[1] < 480:
            return
        _last_saved_size = size
    try:
        app.save_window_size(size[0], size[1])
    except Exception:
        pass


def install_file_drop(window, app: App) -> None:
    """Keep dropped files on this page and add their real paths to the queue.

    The desktop window only reports a full path when a drop listener is registered.
    Without that listener, WebView2 opens each dropped file instead.
    """
    try:
        from webview.dom import DOMEventHandler
    except Exception as exc:
        print(f"Drag and drop is unavailable ({exc}). Use Add files.", flush=True)
        return

    def on_drop(event) -> None:
        claimed = False
        try:
            files = _dropped_files(event)
            if not files:
                return
            paths = []
            for item in files:
                path = item.get("pywebviewFullPath") or item.get("path") or ""
                if path:
                    paths.append(str(path))
            if not paths:
                # The page still has the file bytes and will add them itself.
                return
            app.note_drop()
            claimed = True
            result = app.add_paths(paths)
            if result.get("message"):
                app._set_notice(str(result["message"]))
        except Exception as exc:
            if not claimed:
                app.note_drop()
            app._set_notice(str(exc))

    try:
        # dragover is handled in the page. A Python listener here would run on every
        # drag tick. The drop listener is what receives the real file paths.
        window.dom.document.on("drop", DOMEventHandler(on_drop, prevent_default=True))
        window.evaluate_js("window.__justprintDrop = true")
    except Exception as exc:
        print(f"Drag and drop setup failed ({exc}). Use Add files.", flush=True)


def _dropped_files(event) -> list[dict]:
    transfer = (event or {}).get("dataTransfer") or {}
    files = transfer.get("files") or []
    if isinstance(files, dict):
        files = list(files.values())
    if not isinstance(files, list):
        return []
    return [item for item in files if isinstance(item, dict)]


def _wait_until_listening(httpd, timeout: float = 5) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(httpd.server_address, timeout=0.2):
                return
        except OSError:
            time.sleep(0.02)
    raise RuntimeError("JustPrint did not start")


if __name__ == "__main__":
    main()

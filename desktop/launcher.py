"""Resumeyar Windows launcher: runs the local Flask app in a native window."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import webview

FROZEN = bool(getattr(sys, "frozen", False))
HEADLESS = "--headless" in sys.argv
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Resumeyar"
LOG_PATH = DATA_DIR / "launcher.log"

os.environ["RESUMEYAR_ROOT"] = str(ROOT)
os.environ["RESUMEYAR_DATA"] = str(DATA_DIR)
os.environ["RESUMEYAR_NO_BROWSER"] = "1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _setup_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def _free_port() -> int:
    for port in range(5533, 5563):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("هیچ پورت آزادی بین 5533 تا 5562 پیدا نشد.")


def _show_message(text: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        None, text, "رزومه یار", 0x40 | 0x10000
    )


def _acquire_instance_lock():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, "ResumeyarDesktopInstance")
    if ctypes.get_last_error() == 183:
        return None
    return handle


class Server:
    def __init__(self) -> None:
        self.port = 0
        self.url = ""
        self.server = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._run, name="resumeyar-http", daemon=True).start()

    def _run(self) -> None:
        try:
            import app as webapp
            from werkzeug.serving import make_server

            self.port = _free_port()
            self.url = f"http://127.0.0.1:{self.port}/"
            server = make_server("127.0.0.1", self.port, webapp.app, threaded=True)
            server.daemon_threads = True
            with self.lock:
                self.server = server
            logging.info("serving on %s", self.url)
            server.serve_forever()
        except Exception as exc:
            self.error = f"{exc.__class__.__name__}: {exc}"
            logging.exception("server failed")
            traceback.print_exc()

    def stop(self) -> None:
        with self.lock:
            server = self.server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                logging.exception("server shutdown failed")


def _error_page(message: str) -> str:
    safe = (
        message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f"""<!doctype html>
<html lang="fa" dir="rtl"><meta charset="utf-8">
<body style="margin:0;background:#102a43;color:#f2efe6;font-family:Tahoma,sans-serif;
             display:flex;align-items:center;justify-content:center;height:100vh">
  <div style="max-width:460px;padding:24px;text-align:center">
    <h2 style="color:#b08d3f">راه‌اندازی برنامه ناموفق بود</h2>
    <p style="color:#bcc9cf;line-height:2">فایل لاگ را در پوشه داده‌ها ببینید.</p>
    <pre style="direction:ltr;text-align:left;background:#173952;padding:12px;
                border-radius:8px;white-space:pre-wrap">{safe}</pre>
  </div>
</body></html>"""


def main() -> None:
    _setup_logging()
    logging.info("launcher start frozen=%s root=%s", FROZEN, ROOT)

    if not HEADLESS:
        lock = _acquire_instance_lock()
        if lock is None:
            logging.info("another instance is already running")
            _show_message(
                "رزومه یار از قبل باز است. پنجره فعلی را ببندید و دوباره اجرا کنید."
            )
            return

    server = Server()
    server.start()
    deadline = time.time() + 15
    while not server.url and not server.error and time.time() < deadline:
        time.sleep(0.05)

    webview.settings["ALLOW_DOWNLOADS"] = True

    if server.error:
        webview.create_window("رزومه یار", html=_error_page(server.error),
                              width=560, height=340)
        webview.start()
        return

    logging.info("window opening %s", server.url)

    if HEADLESS:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
        return

    window = webview.create_window(
        "رزومه یار",
        server.url,
        width=1280,
        height=900,
        min_size=(1000, 680),
        text_select=True,
        zoomable=True,
    )

    def on_closed() -> None:
        threading.Thread(target=server.stop, daemon=True).start()

    window.events.closed += on_closed

    loaded = threading.Event()

    def on_loaded() -> None:
        loaded.set()

    window.events.loaded += on_loaded

    def load_watchdog() -> None:
        if loaded.wait(45):
            return
        logging.error("window did not finish loading within 45s")
        _show_message(
            "نمایشگر برنامه بالا نیامد. برنامه بسته می‌شود؛ دوباره اجرا کنید. "
            "اگر تکرار شد، از نصب بودن WebView2 مطمئن شوید."
        )
        try:
            window.destroy()
        except Exception:
            logging.exception("window destroy failed")

    threading.Thread(target=load_watchdog, name="load-watchdog", daemon=True).start()

    icon = ASSETS / "resumeyar.ico"
    start_kwargs = {"private_mode": False, "storage_path": str(DATA_DIR / "webview")}
    if icon.exists():
        start_kwargs["icon"] = str(icon)

    try:
        webview.start(**start_kwargs)
    except Exception:
        logging.exception("webview failed")
        _show_message(
            "پنجره برنامه باز نشد. خطا در فایل لاگ ثبت شد؛ برنامه را دوباره اجرا کنید."
        )
    finally:
        server.stop()


if __name__ == "__main__":
    main()

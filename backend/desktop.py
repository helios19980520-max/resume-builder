"""
Desktop entry point: runs the API + built web UI in one process and opens the browser.
Used by the PyInstaller build (ResumeBuilder.exe) and runnable directly:  python desktop.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, preferred + 1, preferred + 2, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return 0


def main() -> None:
    # PyInstaller: make the bundled package importable and keep temp/data paths sane
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        sys.path.insert(0, base)
        os.environ.setdefault("STATIC_DIR", os.path.join(base, "static"))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        os.environ.setdefault("STATIC_DIR", os.path.join(here, "static"))

    import uvicorn

    from app import config  # noqa: E402  (sets DATA_DIR)
    from app.main import app  # noqa: E402

    port = int(os.getenv("PORT", "0")) or _free_port()
    url = f"http://127.0.0.1:{port}"
    print("=" * 64)
    print(" Resume Builder")
    print(f" Open {url} in your browser (opening automatically…)")
    print(f" Your data: {config.DATA_DIR}")
    print(" Keep this window open while you use the app. Close it to quit.")
    print("=" * 64, flush=True)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    if not os.getenv("NO_BROWSER"):
        webbrowser.open(url)
    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True
        t.join(timeout=5)


if __name__ == "__main__":
    main()

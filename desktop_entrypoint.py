"""
Desktop Standalone Entrypoint for Grabber.
Directly bootstraps Streamlit in-process and opens the local browser.
Designed for PyInstaller standalone executables (.exe, .app, Linux binary).

Copyright (c) 2026 Gabriele Vianello <vianello.tech@gmail.com>.
Licensed under Grabber Restrictive Non-Commercial License (RNC-1.0).
"""

import contextlib
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from streamlit.web import bootstrap


def get_base_dir() -> Path:
    """Return base directory whether running from source or PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller frozen executable
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is available on the specified host."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform != "win32":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_free_port(preferred_port: int = 8501, max_tries: int = 50, host: str = "127.0.0.1") -> int:
    """Find an available TCP port on host starting from preferred_port."""
    for port in range(preferred_port, preferred_port + max_tries):
        if is_port_available(port, host):
            return port

    # Fallback to an ephemeral port allocated by the OS
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def launch_browser_when_ready(
    host: str,
    port: int,
    timeout_seconds: float = 15.0,
    poll_interval: float = 0.15,
) -> bool:
    """Poll the server health endpoint and open the browser once ready."""
    url = f"http://{host}:{port}"
    health_url = f"http://{host}:{port}/_stcore/health"
    start_time = time.time()

    # Create proxy-free opener to bypass corporate proxies and VPN loopback interceptors
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "Grabber-HealthCheck/1.0"},
            )
            with opener.open(req, timeout=1.0) as resp:
                if resp.status == 200:
                    webbrowser.open(url)
                    return True
        except Exception:
            time.sleep(poll_interval)

    # Fallback: if healthcheck polling timed out, attempt to open browser anyway
    webbrowser.open(url)
    return False


def build_flag_options(port: int, host: str = "127.0.0.1") -> dict[str, Any]:
    """Build Streamlit configuration flags for desktop execution."""
    return {
        "server.headless": True,
        "browser.gatherUsageStats": False,
        "server.address": host,
        "browser.serverAddress": host,
        "server.port": port,
        "server.enableCORS": False,
        "server.enableXsrfProtection": False,
        "global.developmentMode": False,
    }


def main():
    base_dir = get_base_dir()
    app_path = base_dir / "src" / "ui" / "app.py"

    # Ensure src is in sys.path
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    host = "127.0.0.1"
    port = find_free_port(preferred_port=8501, host=host)
    flag_options = build_flag_options(port=port, host=host)

    # Launch browser monitor in background daemon thread
    browser_thread = threading.Thread(
        target=launch_browser_when_ready,
        args=(host, port),
        daemon=True,
    )
    browser_thread.start()

    # Start Streamlit in-process
    try:
        # bootstrap.run() does not apply flag_options by itself: `streamlit run` loads them first.
        # Skipping this leaves global.developmentMode=True in a frozen bundle (Streamlit is not under
        # site-packages), which disables the frontend static routes -> "Not Found" on "/".
        bootstrap.load_config_options(flag_options)
        bootstrap.run(
            str(app_path),
            is_hello=False,
            args=[],
            flag_options=flag_options,
        )
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        with contextlib.suppress(Exception):
            from src.core.paths import get_app_cache_dir

            err_log = get_app_cache_dir() / "startup_error.log"
            err_log.write_text(f"Grabber desktop startup error:\n{exc}\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()

"""
Desktop Standalone Entrypoint for Grabber.
Runs the Streamlit server in a child process (same executable, ``--serve PORT``) and shows the UI in a
native window (pywebview), so the app has a real Dock/taskbar presence and quits with its window.
Falls back to the system browser when no native webview backend is available (e.g. Linux without GTK/Qt).
Designed for PyInstaller standalone executables (.exe, .app, Linux binary).

Copyright (c) 2026 Gabriele Vianello <vianello.tech@gmail.com>.
Licensed under Grabber Restrictive Non-Commercial License (RNC-1.0).
"""

import argparse
import contextlib
import html
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from streamlit.web import bootstrap

APP_TITLE = "Grabber"
SERVER_FLAG = "--serve"
PARENT_PID_FLAG = "--parent-pid"
STARTUP_TIMEOUT_SECONDS = 60.0

_PAGE_STYLE = (
    "html,body{height:100%;margin:0;font:16px -apple-system,'Segoe UI',sans-serif;background:#fff;color:#262730}"
    "body{display:flex;align-items:center;justify-content:center;text-align:center;padding:0 24px}"
    "@media(prefers-color-scheme:dark){html,body{background:#0e1117;color:#fafafa}}"
)
SPLASH_HTML = f"<!doctype html><meta charset='utf-8'><title>{APP_TITLE}</title><style>{_PAGE_STYLE}</style><div>Avvio di {APP_TITLE}&hellip;</div>"
ERROR_HTML = (
    f"<!doctype html><meta charset='utf-8'><title>{APP_TITLE}</title><style>{_PAGE_STYLE}</style>"
    "<div><h2>Impossibile avviare il motore di Grabber</h2><p>Dettagli nel file di log:<br><code>__LOG__</code></p></div>"
)


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


def wait_until_healthy(
    host: str,
    port: int,
    timeout_seconds: float = 15.0,
    poll_interval: float = 0.15,
    is_alive: Callable[[], bool] | None = None,
) -> bool:
    """Poll the Streamlit health endpoint until it answers 200, the timeout expires or the server dies."""
    health_url = f"http://{host}:{port}/_stcore/health"
    start_time = time.time()

    # Create proxy-free opener to bypass corporate proxies and VPN loopback interceptors
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)

    while time.time() - start_time < timeout_seconds:
        if is_alive is not None and not is_alive():
            return False
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "Grabber-HealthCheck/1.0"},
            )
            with opener.open(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(poll_interval)
    return False


def launch_browser_when_ready(
    host: str,
    port: int,
    timeout_seconds: float = 15.0,
    poll_interval: float = 0.15,
) -> bool:
    """Poll the server health endpoint and open the browser once ready."""
    ready = wait_until_healthy(host, port, timeout_seconds, poll_interval)
    # Fallback: if healthcheck polling timed out, attempt to open browser anyway
    webbrowser.open(f"http://{host}:{port}")
    return ready


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse internal flags; unknown args (e.g. macOS ``-psn_*``) are ignored."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(SERVER_FLAG, dest="serve_port", type=int, default=None)
    parser.add_argument(PARENT_PID_FLAG, dest="parent_pid", type=int, default=None)
    args, _ = parser.parse_known_args(argv)
    return args


def build_server_cmd(port: int, parent_pid: int | None = None) -> list[str]:
    """Command that re-runs this entrypoint as the headless Streamlit server."""
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve())]
    cmd += [SERVER_FLAG, str(port)]
    if parent_pid is not None:
        cmd += [PARENT_PID_FLAG, str(parent_pid)]
    return cmd


def _prepare_sys_path() -> Path:
    base_dir = get_base_dir()
    # Ensure src is in sys.path
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    return base_dir


def _watch_parent(parent_pid: int, interval: float = 2.0) -> None:
    """Shut this server down when the GUI process dies without cleaning up (crash, kill -9)."""
    import psutil

    while psutil.pid_exists(parent_pid):
        time.sleep(interval)
    os.kill(os.getpid(), signal.SIGTERM)


def run_server(port: int, parent_pid: int | None = None) -> None:
    """Run the Streamlit server in this process (blocks until it is stopped)."""
    base_dir = _prepare_sys_path()
    app_path = base_dir / "src" / "ui" / "app.py"
    flag_options = build_flag_options(port=port, host="127.0.0.1")

    if parent_pid is not None:
        threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()

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


def _server_log_path() -> Path | None:
    with contextlib.suppress(Exception):
        from src.core.paths import get_app_cache_dir

        return get_app_cache_dir() / "server.log"
    return None


def start_server_process(port: int) -> tuple[subprocess.Popen[bytes], Path | None]:
    """Spawn the Streamlit server child, logging its output to the cache dir."""
    log_path = _server_log_path()
    log_file: Any = subprocess.DEVNULL
    if log_path is not None:
        with contextlib.suppress(OSError):
            log_file = open(log_path, "wb")  # noqa: SIM115 - handed to the child, closed below
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(
            build_server_cmd(port, parent_pid=os.getpid()),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    finally:
        if log_file is not subprocess.DEVNULL:
            log_file.close()
    return proc, log_path


def stop_server_process(proc: subprocess.Popen[bytes], timeout: float = 10.0) -> None:
    """Terminate the server child gracefully, killing it if it does not exit in time."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_native_window(host: str, port: int, proc: subprocess.Popen[bytes], log_path: Path | None) -> bool:
    """Show the UI in a native window; blocks until it is closed.

    Returns False when no native webview backend is available, so the caller can fall back to the browser.
    """
    try:
        import webview
    except Exception:
        return False

    webview.settings["ALLOW_DOWNLOADS"] = True  # st.download_button / exports
    window = webview.create_window(APP_TITLE, html=SPLASH_HTML, width=1440, height=900, min_size=(960, 640))

    def show_app() -> None:
        if wait_until_healthy(host, port, STARTUP_TIMEOUT_SECONDS, is_alive=lambda: proc.poll() is None):
            window.load_url(f"http://{host}:{port}")
        else:
            window.load_html(ERROR_HTML.replace("__LOG__", html.escape(str(log_path or "n/d"))))

    try:
        webview.start(show_app)
    except Exception:
        return False
    return True


def run_desktop() -> None:
    """GUI process: server child + native window (browser fallback)."""
    _prepare_sys_path()
    host = "127.0.0.1"
    port = find_free_port(preferred_port=8501, host=host)
    proc, log_path = start_server_process(port)
    try:
        if not run_native_window(host, port, proc, log_path):
            launch_browser_when_ready(host, port)
            proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_server_process(proc)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.serve_port is not None:
        run_server(args.serve_port, args.parent_pid)
    else:
        run_desktop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()

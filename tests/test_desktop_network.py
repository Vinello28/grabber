"""Unit tests for desktop network configuration, port discovery, and loopback resolution.

Ensures that Grabber binds deterministically to 127.0.0.1 on Windows, macOS, and Linux,
preventing 'Access to localhost was denied' (ERR_NETWORK_ACCESS_DENIED / HTTP 403)
and race conditions on browser startup.
"""

import http.server
import socket
import threading
from pathlib import Path
from unittest.mock import patch

from desktop_entrypoint import (
    build_flag_options,
    find_free_port,
    is_port_available,
    launch_browser_when_ready,
)
from run import build_streamlit_cmd


def test_is_port_available_free_port():
    # Reserve an ephemeral port and close it immediately
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    # Port should now be available
    assert is_port_available(free_port, host="127.0.0.1") is True


def test_is_port_available_occupied_port():
    # Keep a socket actively listening
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        occupied_port = s.getsockname()[1]

        # Port must be reported as unavailable
        assert is_port_available(occupied_port, host="127.0.0.1") is False


def test_find_free_port_prefers_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        target_port = s.getsockname()[1]

    port = find_free_port(preferred_port=target_port, max_tries=5, host="127.0.0.1")
    assert port == target_port


def test_find_free_port_skips_occupied_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        busy_port = s.getsockname()[1]

        # find_free_port starting at busy_port should skip it
        allocated = find_free_port(preferred_port=busy_port, max_tries=10, host="127.0.0.1")
        assert allocated != busy_port
        assert allocated > 0


def test_find_free_port_ephemeral_fallback():
    # When max_tries=0, should fallback to ephemeral port allocated by OS
    allocated = find_free_port(preferred_port=8501, max_tries=0, host="127.0.0.1")
    assert isinstance(allocated, int)
    assert allocated > 1024


def test_build_flag_options_configuration():
    flags = build_flag_options(port=8542, host="127.0.0.1")
    assert flags["server.address"] == "127.0.0.1"
    assert flags["browser.serverAddress"] == "127.0.0.1"
    assert flags["server.port"] == 8542
    assert flags["server.enableCORS"] is False
    assert flags["server.enableXsrfProtection"] is False
    assert flags["server.headless"] is True
    assert flags["browser.gatherUsageStats"] is False
    assert flags["global.developmentMode"] is False


class _MockHealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/_stcore/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Silence console log noise during testing
        pass


def test_launch_browser_when_ready_success():
    # Start temporary mock HTTP server representing Streamlit health endpoint
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHealthHandler)
    mock_port = server.server_port

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    opened_urls = []
    with patch("webbrowser.open", side_effect=opened_urls.append):
        ready = launch_browser_when_ready(
            host="127.0.0.1",
            port=mock_port,
            timeout_seconds=3.0,
            poll_interval=0.05,
        )

    server.server_close()
    assert ready is True
    assert opened_urls == [f"http://127.0.0.1:{mock_port}"]


def test_launch_browser_when_ready_fallback_on_timeout():
    # Pick a port with no listener to trigger timeout fallback
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        dead_port = s.getsockname()[1]

    opened_urls = []
    with patch("webbrowser.open", side_effect=opened_urls.append):
        ready = launch_browser_when_ready(
            host="127.0.0.1",
            port=dead_port,
            timeout_seconds=0.2,
            poll_interval=0.05,
        )

    assert ready is False
    # Fallback still opens browser
    assert opened_urls == [f"http://127.0.0.1:{dead_port}"]


def test_build_streamlit_cmd():
    cmd = build_streamlit_cmd("python", Path("/dummy/app.py"))
    assert "--server.address=127.0.0.1" in cmd
    assert "--browser.serverAddress=127.0.0.1" in cmd
    assert "--server.enableCORS=false" in cmd
    assert "--server.enableXsrfProtection=false" in cmd
    assert "--server.headless=false" in cmd
    assert "--browser.gatherUsageStats=false" in cmd




def test_main_loads_config_options_before_starting_streamlit():
    """Regression: flags passed to bootstrap.run() are NOT applied unless loaded first.

    Without bootstrap.load_config_options(), a PyInstaller bundle runs with
    global.developmentMode=True (Streamlit is not under site-packages), so the
    frontend static routes are not mounted: GET / returns 404 "Not Found" while
    /_stcore/health still answers ok. server.port / address / CORS flags are ignored too.
    """
    import desktop_entrypoint

    calls: list[str] = []
    flags = build_flag_options(port=8765)

    with (
        patch.object(desktop_entrypoint, "find_free_port", return_value=8765),
        patch.object(desktop_entrypoint.threading, "Thread"),
        patch.object(
            desktop_entrypoint.bootstrap,
            "load_config_options",
            side_effect=lambda opts: calls.append(f"load:{opts == flags}"),
        ),
        patch.object(
            desktop_entrypoint.bootstrap,
            "run",
            side_effect=lambda *a, **k: calls.append("run"),
        ),
    ):
        desktop_entrypoint.main()

    assert calls == ["load:True", "run"]


def test_desktop_flags_disable_development_mode_in_streamlit_config():
    """Loading the desktop flags must yield production mode on the chosen loopback port."""
    import subprocess
    import sys

    code = (
        "from streamlit import config\n"
        "from streamlit.web import bootstrap\n"
        "from desktop_entrypoint import build_flag_options\n"
        "bootstrap.load_config_options(build_flag_options(port=8765))\n"
        "print(config.get_option('global.developmentMode'),"
        " config.get_option('server.port'),"
        " config.get_option('server.address'),"
        " config.get_option('server.headless'))\n"
    )
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, check=True, timeout=60
    )
    assert result.stdout.strip().splitlines()[-1] == "False 8765 127.0.0.1 True"

"""
Tests for the live system-stats panel.
The panel must refresh on its own every 5 seconds via a Streamlit fragment, so that only the
panel reruns (not the whole script, which would re-render filters/tables and hit DuckDB).
"""

import importlib

import streamlit as st
from streamlit.testing.v1 import AppTest

import src.ui.components.system_stats as system_stats


def test_refresh_interval_is_five_seconds():
    assert system_stats.SYSTEM_STATS_REFRESH_SECONDS == 5


def test_panel_is_a_fragment_with_auto_rerun(monkeypatch):
    """The render function is wrapped by st.fragment(run_every=<interval>)."""
    captured: dict = {}
    real_fragment = st.fragment

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_fragment(*args, **kwargs)

    monkeypatch.setattr(st, "fragment", spy)
    try:
        importlib.reload(system_stats)
        assert captured.get("run_every") == system_stats.SYSTEM_STATS_REFRESH_SECONDS
    finally:
        monkeypatch.undo()
        importlib.reload(system_stats)


def test_panel_renders_all_metrics():
    def script():
        import streamlit as st

        from src.ui.components.system_stats import render_system_stats

        with st.sidebar:
            render_system_stats()

    at = AppTest.from_function(script).run()
    assert not at.exception
    labels = {m.label for m in at.sidebar.metric}
    assert labels == {"RAM Processo", "Core CPU", "RAM Libera", "CPU Utilizzo"}

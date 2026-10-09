"""
System stats UI component.
Displays live RAM, CPU, threads, and memory limit in the Streamlit sidebar.
"""

import streamlit as st

from src.engine.resource_monitor import ResourceMonitor

SYSTEM_STATS_REFRESH_SECONDS = 5


@st.fragment(run_every=SYSTEM_STATS_REFRESH_SECONDS)
def render_system_stats():
    """Render hardware resource monitor, refreshing itself every few seconds.

    Being a fragment, only this panel reruns on the timer (not the whole script). It must be
    called inside the container where it should appear (``with st.sidebar:``): a fragment
    replaces its own content on rerun, but would append to an externally-created container.
    """
    stats = ResourceMonitor.get_system_stats()

    st.markdown("### 🖥️ Risorse di Sistema")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("RAM Processo", f"{stats['process_rss_mb']} MB")
        st.metric("Core CPU", f"{stats['cpu_cores']}")
    with c2:
        st.metric("RAM Libera", f"{stats['available_ram_gb']} GB")
        st.metric("CPU Utilizzo", f"{stats['cpu_percent']}%")

    st.caption(f"Limite memoria motore: **{ResourceMonitor.calculate_safe_memory_limit()}**")
    st.divider()

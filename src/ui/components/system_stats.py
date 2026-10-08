"""
System stats UI component.
Displays live RAM, CPU, threads, and memory limit in the Streamlit sidebar.
"""

import streamlit as st

from src.engine.resource_monitor import ResourceMonitor


def render_system_stats():
    """Render hardware resource monitor in the sidebar."""
    stats = ResourceMonitor.get_system_stats()

    st.sidebar.markdown("### 🖥️ Risorse di Sistema")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        st.metric("RAM Processo", f"{stats['process_rss_mb']} MB")
        st.metric("Core CPU", f"{stats['cpu_cores']}")
    with c2:
        st.metric("RAM Libera", f"{stats['available_ram_gb']} GB")
        st.metric("CPU Utilizzo", f"{stats['cpu_percent']}%")

    st.sidebar.caption(f"Limite memoria motore: **{ResourceMonitor.calculate_safe_memory_limit()}**")
    st.sidebar.divider()

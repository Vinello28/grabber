"""
Cache management UI component.
Displays disk space occupied by cache files and allows clearing cache.
"""

from __future__ import annotations

import streamlit as st

from src.core.paths import clear_cache, format_bytes, get_cache_size_bytes


def render_cache_controls():
    """Render cache size indicator and clear cache action in sidebar."""
    size_bytes = get_cache_size_bytes()
    size_str = format_bytes(size_bytes)

    with st.sidebar.expander("💾 Gestione Cache", expanded=False):
        st.write(f"Spazio su disco: **{size_str}**")
        st.caption("Include file Parquet convertiti e file di spillover.")

        if st.button("🗑️ Svuota Cache", key="btn_clear_cache", use_container_width=True, disabled=(size_bytes == 0)):
            freed = clear_cache()
            st.success(f"Cache svuotata ({format_bytes(freed)} liberati).")
            st.rerun()

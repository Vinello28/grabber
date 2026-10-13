"""
Cache management UI component.
Displays disk space occupied by cache files and allows clearing cache.
"""

from __future__ import annotations

import contextlib
from typing import Any

import streamlit as st

from src.core.paths import clear_cache, format_bytes, get_cache_size_bytes


@st.fragment
def render_cache_controls(engine: Any = None):
    """Render cache size indicator and clear cache action in sidebar."""
    size_bytes = get_cache_size_bytes()
    size_str = format_bytes(size_bytes)

    with st.expander("💾 Gestione Cache", expanded=False):
        st.write(f"Spazio su disco: **{size_str}**")
        st.caption("Include file Parquet convertiti e file di spillover.")

        if st.button("🗑️ Svuota Cache", key="btn_clear_cache", use_container_width=True, disabled=(size_bytes == 0)):
            freed = clear_cache()
            import gc
            gc.collect()
            if engine and getattr(engine, "current_dataset_path", None):
                with contextlib.suppress(Exception):
                    new_schema = engine.connect_dataset(engine.current_dataset_path)
                    st.session_state["schema"] = new_schema
            gc.collect()
            st.success(f"Cache svuotata ({format_bytes(freed)} liberati).")
            st.rerun()



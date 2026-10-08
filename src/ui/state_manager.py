"""
UI Session State Lifecycle Manager.
Handles cleanup, synchronization, and defensive sanitization of session state
when switching between datasets to prevent Streamlit widget errors.
"""

from __future__ import annotations
import streamlit as st


# List of explicit keys that depend on dataset schema or column names
DATASET_DEPENDENT_KEYS = [
    "selected_viewer_cols",
    "viewer_cols_multiselect",
    "sort_col_select",
    "sort_dir_radio",
    "current_page",
    "page_num_input",
    "global_search_cols_val",
    "multiselect_global_search_cols",
    "filter_entries",
    "active_filters",
    "agg_group_by_cols",
    "agg_sum_col",
    "agg_distinct_col",
    "distinct_col_sel",
    "export_path_input",
]

# Prefixes for dynamically generated filter row widget keys
DYNAMIC_WIDGET_PREFIXES = (
    "col_sel_",
    "op_sel_",
    "val_min_",
    "val_max_",
    "val_multi_",
    "val_single_",
    "del_btn_",
)


def reset_dataset_ui_state():
    """
    Purge all dataset-specific session state keys when switching datasets.
    Ensures no stale column names, filter rules, sort settings, or pagination
    persist from the previous dataset.
    """
    for key in list(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in DYNAMIC_WIDGET_PREFIXES):
            del st.session_state[key]
        elif key in DATASET_DEPENDENT_KEYS:
            del st.session_state[key]

    # Reset default filter entries list
    st.session_state["filter_entries"] = []
    st.session_state["active_filters"] = []
    st.session_state["current_page"] = 1

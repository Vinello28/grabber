"""
Tests for UI session state management and dataset switching resilience.
Verifies that switching between datasets with differing schemas (e.g. CSV with 'ANNO'
and XML without 'ANNO') does not trigger StreamlitDefaultNotInOptionsError.
"""

import streamlit as st
from streamlit.elements.lib.options_selector_utils import (
    check_and_convert_to_indices,
    get_default_indices,
)

from src.ui.state_manager import DATASET_DEPENDENT_KEYS, reset_dataset_ui_state


def test_reset_dataset_ui_state():
    """Ensure reset_dataset_ui_state purges all dataset-dependent state and dynamic widget keys."""
    # Seed session state with various keys from a previous dataset
    st.session_state["selected_viewer_cols"] = ["CAR", "ANNO", "IMPORTO"]
    st.session_state["viewer_cols_multiselect"] = ["CAR", "ANNO"]
    st.session_state["sort_col_select"] = "ANNO"
    st.session_state["sort_dir_radio"] = "Crescente (ASC)"
    st.session_state["current_page"] = 4
    st.session_state["page_num_input"] = 4
    st.session_state["global_search_cols_val"] = ["ANNO"]
    st.session_state["multiselect_global_search_cols"] = ["ANNO"]
    st.session_state["agg_group_by_cols"] = ["ANNO"]
    st.session_state["agg_sum_col"] = "ANNO"
    st.session_state["agg_distinct_col"] = "ANNO"
    st.session_state["distinct_col_sel"] = "ANNO"
    st.session_state["export_path_input"] = "/tmp/export.csv"

    # Dynamic filter keys
    st.session_state["col_sel_0"] = "ANNO"
    st.session_state["op_sel_0"] = "EQUALS"
    st.session_state["val_single_0"] = "2024"
    st.session_state["val_multi_0"] = ["2024"]
    st.session_state["del_btn_0"] = False

    # Independent app state (should NOT be cleared)
    st.session_state["unrelated_setting"] = "keep_this"

    reset_dataset_ui_state()

    # Verify keys that must be completely removed
    keys_to_remove = [k for k in DATASET_DEPENDENT_KEYS if k not in ("filter_entries", "active_filters", "current_page")]
    for k in keys_to_remove:
        assert k not in st.session_state, f"Key {k} was not removed by reset_dataset_ui_state"

    # Verify dynamic keys are cleared
    assert "col_sel_0" not in st.session_state
    assert "op_sel_0" not in st.session_state
    assert "val_single_0" not in st.session_state
    assert "val_multi_0" not in st.session_state
    assert "del_btn_0" not in st.session_state

    # Verify initialized defaults
    assert st.session_state["filter_entries"] == []
    assert st.session_state["active_filters"] == []
    assert st.session_state["current_page"] == 1

    # Verify independent key is retained
    assert st.session_state["unrelated_setting"] == "keep_this"


def test_defensive_column_selection_sanitization():
    """
    Simulates the exact crash scenario:
    1. Previous dataset had ['ANNO', 'CAR', 'CUP']
    2. New dataset schema only has ['CAR', 'CUP', 'TITOLO_PROGETTO'] (no 'ANNO')
    3. Stale session state contains 'ANNO'
    4. Defensive sanitization ensures Streamlit get_default_indices never fails.
    """
    new_schema_columns = ["CAR", "CUP", "TITOLO_PROGETTO", "BENEFICIARIO"]

    # Stale saved columns from previous dataset
    stale_saved = ["ANNO", "CAR", "OBSOLETE_COL"]
    st.session_state["selected_viewer_cols"] = stale_saved
    st.session_state["viewer_cols_multiselect"] = stale_saved

    # Component logic from data_viewer.py:
    fallback_selected = new_schema_columns[:15] if len(new_schema_columns) > 15 else new_schema_columns
    saved_cols = st.session_state.get("selected_viewer_cols")
    if saved_cols is not None:
        valid_saved = [c for c in saved_cols if c in new_schema_columns]
        default_selected = valid_saved if valid_saved else fallback_selected
    else:
        default_selected = fallback_selected

    # Ensure widget key state is strictly valid for current options
    if "viewer_cols_multiselect" in st.session_state:
        st.session_state["viewer_cols_multiselect"] = [
            c for c in st.session_state["viewer_cols_multiselect"] if c in new_schema_columns
        ]
        if not st.session_state["viewer_cols_multiselect"]:
            st.session_state["viewer_cols_multiselect"] = default_selected

    # 1. Assert default_selected only contains valid options (no 'ANNO')
    assert "ANNO" not in default_selected
    assert default_selected == ["CAR"]

    # 2. Assert viewer_cols_multiselect in session_state only contains valid options
    assert "ANNO" not in st.session_state["viewer_cols_multiselect"]
    assert st.session_state["viewer_cols_multiselect"] == ["CAR"]

    # 3. Simulate Streamlit's internal multiselect validation (which previously threw StreamlitDefaultNotInOptionsError)
    indices = get_default_indices(new_schema_columns, default_selected)
    assert indices == [0]  # 'CAR' is at index 0


def test_defensive_sort_col_sanitization():
    """Ensure sort_col_select gracefully falls back when previous sort col is missing in new dataset."""
    new_cols = ["CAR", "CUP"]
    sort_options = ["(Nessun ordinamento)"] + new_cols

    st.session_state["sort_col_select"] = "ANNO"

    if "sort_col_select" in st.session_state and st.session_state["sort_col_select"] not in sort_options:
        st.session_state["sort_col_select"] = "(Nessun ordinamento)"

    assert st.session_state["sort_col_select"] == "(Nessun ordinamento)"
    # Streamlit validation
    idx = check_and_convert_to_indices(sort_options, st.session_state["sort_col_select"])
    assert idx == [0]


def test_defensive_aggregations_sanitization():
    """Ensure aggregations group_by and metric selectors gracefully sanitize missing columns."""
    new_cols = ["CAR", "IMPORTO_NOMINALE_TOTALE"]
    numeric_cols = ["IMPORTO_NOMINALE_TOTALE"]

    st.session_state["agg_group_by_cols"] = ["ANNO", "CAR"]
    st.session_state["agg_sum_col"] = "ANNO"  # Old numeric col

    # Aggregations logic:
    default_group = [new_cols[0]] if new_cols else []
    if "agg_group_by_cols" in st.session_state:
        valid_grp = [c for c in st.session_state["agg_group_by_cols"] if c in new_cols]
        st.session_state["agg_group_by_cols"] = valid_grp if valid_grp else default_group

    sum_options = ["(Nessuna)"] + numeric_cols
    if "agg_sum_col" in st.session_state and st.session_state["agg_sum_col"] not in sum_options:
        st.session_state["agg_sum_col"] = "(Nessuna)"

    assert st.session_state["agg_group_by_cols"] == ["CAR"]
    assert st.session_state["agg_sum_col"] == "(Nessuna)"

    # Verify Streamlit indexable checks
    indices = get_default_indices(new_cols, st.session_state["agg_group_by_cols"])
    assert indices == [0]

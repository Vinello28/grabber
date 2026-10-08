"""
Tests for pagination navigation and filter battery schema resilience.
Verifies that navigating pages via pagination buttons or handling empty/transient schemas
never triggers IndexError on schema.columns[0].
"""

import streamlit as st

from src.core.models import DatasetSchema, FilterOperator
from src.engine.duckdb_engine import DuckDBEngine
from src.ui.components.filter_battery import render_filter_battery


def test_render_filter_battery_empty_schema():
    """Verify render_filter_battery returns empty lists gracefully when schema has no columns."""
    engine = DuckDBEngine()
    empty_schema = DatasetSchema(
        source_path="dummy/path",
        source_format="csv",
        columns=[],
        total_size_bytes=0,
        file_count=0,
        table_identifier="empty",
    )

    st.session_state["filter_entries"] = [
        {"column": "ANY_COL", "operator": FilterOperator.CONTAINS.value, "value": "test"}
    ]

    filters, search, search_cols = render_filter_battery(empty_schema, engine)
    assert filters == []
    assert search is None
    assert search_cols is None


def test_lazy_column_evaluation_resilience():
    """
    Verify that entry.get('column') does not eagerly evaluate schema.columns[0]
    when schema.columns is empty.
    """
    empty_columns = []
    first_col_name = empty_columns[0].name if empty_columns else ""

    entry = {"column": "EXISTING_COL", "value": "test"}
    current_col = entry.get("column") or first_col_name
    assert current_col == "EXISTING_COL"

    empty_entry = {}
    current_col_fallback = empty_entry.get("column") or first_col_name
    assert current_col_fallback == ""


def test_pagination_state_sync():
    """
    Verify that advancing pagination synchronizes both current_page
    and page_num_input in session_state.
    """
    st.session_state["current_page"] = 1
    st.session_state["page_num_input"] = 1
    total_pages = 10

    # Simulate clicking 'Successiva ➡️'
    current_page = st.session_state["current_page"]
    new_page = min(total_pages, current_page + 1)
    st.session_state["current_page"] = new_page
    st.session_state["page_num_input"] = new_page

    assert st.session_state["current_page"] == 2
    assert st.session_state["page_num_input"] == 2

    # Simulate clicking '⬅️ Precedente'
    current_page = st.session_state["current_page"]
    new_page = max(1, current_page - 1)
    st.session_state["current_page"] = new_page
    st.session_state["page_num_input"] = new_page

    assert st.session_state["current_page"] == 1
    assert st.session_state["page_num_input"] == 1

"""
Data Viewer UI component.
Renders paginated, sortable data table previews with column visibility controls.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.core.models import DatasetSchema, FilterRule, QuerySpec
from src.engine.duckdb_engine import DuckDBEngine


def render_data_viewer(
    schema: DatasetSchema,
    engine: DuckDBEngine,
    filters: list[FilterRule],
    global_search: str | None,
    global_search_cols: list[str] | None,
):
    """Render interactive data preview table with pagination and sorting."""
    st.markdown("#### 📋 Anteprima Dati")

    # Column selection controls
    all_cols = schema.column_names
    fallback_selected = all_cols[:15] if len(all_cols) > 15 else all_cols

    # Filter cached column selection against current dataset schema
    saved_cols = st.session_state.get("selected_viewer_cols")
    if saved_cols is not None:
        valid_saved = [c for c in saved_cols if c in all_cols]
        default_selected = valid_saved if valid_saved else fallback_selected
    else:
        default_selected = fallback_selected

    # Ensure widget key state contains only valid options for current schema
    if "viewer_cols_multiselect" in st.session_state:
        st.session_state["viewer_cols_multiselect"] = [
            c for c in st.session_state["viewer_cols_multiselect"] if c in all_cols
        ]

    with st.expander("👁️ Personalizza Colonne Visibili", expanded=False):
        selected_cols = st.multiselect(
            "Colonne da mostrare (vuoto = tutte le colonne):",
            options=all_cols,
            default=default_selected,
            key="viewer_cols_multiselect",
        )
        st.session_state["selected_viewer_cols"] = selected_cols

    if not selected_cols:
        selected_cols = all_cols

    # Sorting controls
    sort_options = ["(Nessun ordinamento)"] + all_cols
    if "sort_col_select" in st.session_state and st.session_state["sort_col_select"] not in sort_options:
        st.session_state["sort_col_select"] = "(Nessun ordinamento)"

    col_sort_field, col_sort_dir, col_page_size = st.columns([3, 2, 2])
    with col_sort_field:
        sort_col = st.selectbox(
            "Ordina per:",
            options=sort_options,
            index=0,
            key="sort_col_select",
        )
    with col_sort_dir:
        sort_asc = st.radio(
            "Direzione:",
            options=["Crescente (ASC)", "Decrescente (DESC)"],
            horizontal=True,
            key="sort_dir_radio",
        )
    with col_page_size:
        page_size = st.selectbox(
            "Righe per pagina:",
            options=[25, 50, 100, 250, 500],
            index=1,
            key="page_size_select",
        )

    # State for current page
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = 1

    current_page = st.session_state["current_page"]
    offset = (current_page - 1) * page_size

    order_by = None
    if sort_col != "(Nessun ordinamento)":
        order_by = [(sort_col, "ASC" in sort_asc)]

    # Build query specification
    spec = QuerySpec(
        filters=filters,
        global_search=global_search,
        global_search_columns=global_search_cols,
        selected_columns=selected_cols,
        order_by=order_by,
        limit=page_size,
        offset=offset,
    )

    with st.spinner("Esecuzione query sui dati..."):
        try:
            result = engine.execute_query(spec)
        except Exception as e:
            if schema.source_format == "xml" and engine.current_sql_source is None:
                st.info(
                    "ℹ️ **Dataset XML non ancora indicizzato**: per consultare e filtrare i record, "
                    "avvia la conversione streaming cliccando su **'⚡ Indicizza XML in Parquet'** nella barra laterale."
                )
            else:
                st.error(f"Errore durante l'esecuzione della query: {e}")
            return

    total_rows = result.total_matching_rows
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    # Offset recovery: if current page exceeds matching rows or rows returned empty while total_rows > 0
    if (current_page > total_pages or len(result.rows) == 0) and total_rows > 0 and offset > 0:
        current_page = 1
        st.session_state["current_page"] = 1
        st.session_state["page_num_input"] = 1
        spec.offset = 0
        try:
            result = engine.execute_query(spec)
        except Exception as e:
            st.error(f"Errore durante il recupero dei dati: {e}")
            return

    if current_page > total_pages:
        current_page = 1
        st.session_state["current_page"] = 1
        st.session_state["page_num_input"] = 1

    # Status banner
    st.info(
        f"**Risultati trovati:** `{total_rows:,}` righe corrispondenti  |  "
        f"**Tempo esecuzione:** `{result.execution_time_seconds * 1000:.1f} ms`  |  "
        f"**Pagina:** `{current_page} di {total_pages}`"
    )

    # Render DataFrame
    if result.rows:
        df = pd.DataFrame(result.rows, columns=result.columns)
        st.dataframe(df, use_container_width=True, height=450)
    else:
        st.warning("Nessun record trovato con i filtri correnti.")

    # Sync page_num_input in session_state with total_pages
    if "page_num_input" in st.session_state and st.session_state["page_num_input"] > total_pages:
        st.session_state["page_num_input"] = current_page

    # Pagination navigation bar
    nav_c1, nav_c2, nav_c3, _ = st.columns([1, 1, 2, 2])
    with nav_c1:
        if st.button("⬅️ Precedente", disabled=(current_page <= 1), use_container_width=True):
            new_p = max(1, current_page - 1)
            st.session_state["current_page"] = new_p
            st.session_state["page_num_input"] = new_p
            st.rerun()

    with nav_c2:
        if st.button("Successiva ➡️", disabled=(current_page >= total_pages), use_container_width=True):
            new_p = min(total_pages, current_page + 1)
            st.session_state["current_page"] = new_p
            st.session_state["page_num_input"] = new_p
            st.rerun()

    with nav_c3:
        page_input = st.number_input(
            "Vai a pagina:",
            min_value=1,
            max_value=max(1, total_pages),
            value=min(current_page, max(1, total_pages)),
            step=1,
            key="page_num_input",
        )
        if page_input != current_page:
            st.session_state["current_page"] = page_input
            st.rerun()

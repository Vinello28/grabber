"""
Dynamic Filter Battery UI component.
Adapts to any dataset schema, generating type-specific filter widgets
(text, numeric, categorical, date) and a global quick search bar.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple
import streamlit as st

from src.core.models import (
    ColumnMeta,
    DataType,
    DatasetSchema,
    FilterOperator,
    FilterRule,
)
from src.engine.duckdb_engine import DuckDBEngine


def get_type_icon(dtype: DataType) -> str:
    if dtype == DataType.NUMERIC:
        return "🔢"
    if dtype == DataType.CATEGORICAL:
        return "🏷️"
    if dtype == DataType.DATE:
        return "📅"
    if dtype == DataType.BOOLEAN:
        return "☑️"
    return "🔤"


def render_filter_battery(
    schema: DatasetSchema,
    engine: DuckDBEngine,
) -> Tuple[List[FilterRule], str | None, List[str] | None]:
    """
    Render global search bar and dynamic typed filter battery.
    Returns: (list_of_filter_rules, global_search_term, global_search_columns)
    """
    if not schema or not schema.columns:
        return [], None, None

    if "filter_entries" not in st.session_state:
        st.session_state["filter_entries"] = []

    # 1. Quick Global Search Bar
    st.markdown("#### 🔍 Ricerca Rapida")
    col_search, col_cols = st.columns([3, 2])

    with col_search:
        global_search = st.text_input(
            "Cerca parola chiave o codice (es. Codice Fiscale, Denominazione...):",
            value=st.session_state.get("global_search_val", ""),
            placeholder="Digita per cercare...",
            key="input_global_search",
        )
        st.session_state["global_search_val"] = global_search

    text_columns = [
        c.name for c in schema.columns
        if c.data_type in (DataType.TEXT, DataType.CATEGORICAL, DataType.UNKNOWN)
    ]

    saved_search_cols = st.session_state.get("global_search_cols_val", [])
    valid_search_cols = [c for c in saved_search_cols if c in text_columns]

    if "multiselect_global_search_cols" in st.session_state:
        st.session_state["multiselect_global_search_cols"] = [
            c for c in st.session_state["multiselect_global_search_cols"] if c in text_columns
        ]

    with col_cols:
        search_cols = st.multiselect(
            "Cerca su colonne specifiche (default: tutte testuali):",
            options=text_columns,
            default=valid_search_cols,
            key="multiselect_global_search_cols",
        )
        st.session_state["global_search_cols_val"] = search_cols

    # 2. Dynamic Column Filters
    st.markdown("#### ⚙️ Batteria Filtri Dinamici")

    col_btn_add, col_btn_clear, _ = st.columns([1.5, 1.5, 5])
    with col_btn_add:
        if st.button("➕ Aggiungi Filtro", use_container_width=True):
            first_col_name = schema.columns[0].name if schema.columns else ""
            st.session_state["filter_entries"].append({
                "column": first_col_name,
                "operator": FilterOperator.CONTAINS.value,
                "value": "",
                "value_to": "",
            })
            st.rerun()

    with col_btn_clear:
        if st.button("🧹 Rimuovi Tutti", use_container_width=True):
            st.session_state["filter_entries"] = []
            st.session_state["global_search_val"] = ""
            st.rerun()

    filter_rules: List[FilterRule] = []
    entries_to_delete = []

    column_map: Dict[str, ColumnMeta] = {c.name: c for c in schema.columns}
    col_display_options = [f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns]
    col_name_by_display = {f"{get_type_icon(c.data_type)} {c.name}": c.name for c in schema.columns}
    col_display_by_name = {c.name: f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns}

    # Render each filter row
    first_col_name = schema.columns[0].name if schema.columns else ""
    for idx, entry in enumerate(st.session_state["filter_entries"]):
        current_col = entry.get("column") or first_col_name
        if current_col not in column_map:
            current_col = first_col_name
            entry["column"] = current_col
            entry["value"] = ""
            entry["value_to"] = ""

        if not current_col or current_col not in column_map:
            continue

        meta = column_map[current_col]
        dtype = meta.data_type

        col_widget_key = f"col_sel_{idx}"
        if col_widget_key in st.session_state and st.session_state[col_widget_key] not in col_display_options:
            del st.session_state[col_widget_key]

        with st.container(border=True):
            f_cols = st.columns([3, 2.5, 4, 0.8])

            # Select Column
            with f_cols[0]:
                fallback_display = col_display_options[0] if col_display_options else ""
                curr_display = col_display_by_name.get(current_col, fallback_display)
                curr_idx = col_display_options.index(curr_display) if curr_display in col_display_options else 0
                sel_display = st.selectbox(
                    "Colonna",
                    options=col_display_options,
                    index=curr_idx,
                    key=f"col_sel_{idx}",
                )
                selected_col_name = col_name_by_display[sel_display]
                if selected_col_name != current_col:
                    entry["column"] = selected_col_name
                    # reset operator to safe default
                    new_meta = column_map[selected_col_name]
                    entry["operator"] = FilterOperator.BETWEEN.value if new_meta.is_numeric() else FilterOperator.CONTAINS.value
                    entry["value"] = ""
                    st.rerun()

            # Select Operator tailored to type
            with f_cols[1]:
                allowed_ops = _get_allowed_operators(dtype)
                op_labels = {op: _get_op_label(op) for op in allowed_ops}
                curr_op_val = entry.get("operator", allowed_ops[0].value)
                curr_op = FilterOperator(curr_op_val) if curr_op_val in [o.value for o in allowed_ops] else allowed_ops[0]

                sel_op = st.selectbox(
                    "Operatore",
                    options=allowed_ops,
                    format_func=lambda o: op_labels[o],
                    index=allowed_ops.index(curr_op),
                    key=f"op_sel_{idx}",
                )
                entry["operator"] = sel_op.value

            # Input Values tailored to operator & type
            with f_cols[2]:
                val, val_to = _render_value_inputs(idx, entry, sel_op, meta, engine)
                entry["value"] = val
                entry["value_to"] = val_to

            # Delete button
            with f_cols[3]:
                st.write("")
                st.write("")
                if st.button("🗑️", key=f"del_btn_{idx}", help="Rimuovi filtro"):
                    entries_to_delete.append(idx)

            # Build FilterRule object if valid
            if _is_filter_valid(sel_op, val, val_to):
                filter_rules.append(
                    FilterRule(
                        column=selected_col_name,
                        operator=sel_op,
                        value=val,
                        value_to=val_to,
                    )
                )

    # Process deletions
    if entries_to_delete:
        for idx in sorted(entries_to_delete, reverse=True):
            del st.session_state["filter_entries"][idx]
        st.rerun()
    # Proactively reset pagination to page 1 whenever search criteria change
    search_sig = (
        str(global_search.strip() if global_search else ""),
        tuple(sorted(search_cols or [])),
        tuple((r.column, r.operator.value, str(r.value), str(r.value_to)) for r in filter_rules),
    )
    if st.session_state.get("_prev_filter_signature") != search_sig:
        st.session_state["_prev_filter_signature"] = search_sig
        st.session_state["current_page"] = 1
        if "page_num_input" in st.session_state:
            st.session_state["page_num_input"] = 1

    return filter_rules, global_search.strip() or None, search_cols or None


def _get_allowed_operators(dtype: DataType) -> List[FilterOperator]:
    if dtype == DataType.NUMERIC:
        return [
            FilterOperator.BETWEEN,
            FilterOperator.GTE,
            FilterOperator.LTE,
            FilterOperator.GT,
            FilterOperator.LT,
            FilterOperator.EQUALS,
            FilterOperator.NOT_EQUALS,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        ]
    elif dtype == DataType.CATEGORICAL:
        return [
            FilterOperator.IN_LIST,
            FilterOperator.NOT_IN_LIST,
            FilterOperator.CONTAINS,
            FilterOperator.EQUALS,
            FilterOperator.NOT_EQUALS,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        ]
    else:  # Text default
        return [
            FilterOperator.CONTAINS,
            FilterOperator.NOT_CONTAINS,
            FilterOperator.STARTS_WITH,
            FilterOperator.ENDS_WITH,
            FilterOperator.EQUALS,
            FilterOperator.NOT_EQUALS,
            FilterOperator.REGEX,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        ]


def _get_op_label(op: FilterOperator) -> str:
    labels = {
        FilterOperator.CONTAINS: "Contiene",
        FilterOperator.NOT_CONTAINS: "Non contiene",
        FilterOperator.STARTS_WITH: "Inizia con",
        FilterOperator.ENDS_WITH: "Finisce con",
        FilterOperator.EQUALS: "Uguale a",
        FilterOperator.NOT_EQUALS: "Diverso da",
        FilterOperator.REGEX: "Regex",
        FilterOperator.GT: "Maggiore di (>)",
        FilterOperator.GTE: "Maggiore o uguale (>=)",
        FilterOperator.LT: "Minore di (<)",
        FilterOperator.LTE: "Minore o uguale (<=)",
        FilterOperator.BETWEEN: "Intervallo (Tra Min e Max)",
        FilterOperator.IN_LIST: "Incluso tra i selezionati",
        FilterOperator.NOT_IN_LIST: "Escluso dai selezionati",
        FilterOperator.IS_NULL: "È vuoto / nullo",
        FilterOperator.IS_NOT_NULL: "Non è vuoto",
    }
    return labels.get(op, op.value)


def _render_value_inputs(
    idx: int,
    entry: Dict[str, Any],
    op: FilterOperator,
    meta: ColumnMeta,
    engine: DuckDBEngine,
) -> Tuple[Any, Any]:
    if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        st.caption("Nessun parametro richiesto")
        return None, None

    if op == FilterOperator.BETWEEN:
        b_c1, b_c2 = st.columns(2)
        with b_c1:
            min_v = st.text_input(
                "Minimo",
                value=str(entry.get("value", "")),
                key=f"val_min_{idx}",
                placeholder="es. 1000",
            )
        with b_c2:
            max_v = st.text_input(
                "Massimo",
                value=str(entry.get("value_to", "")),
                key=f"val_max_{idx}",
                placeholder="es. 50000",
            )
        return min_v, max_v

    if op in (FilterOperator.IN_LIST, FilterOperator.NOT_IN_LIST):
        # Fetch distinct values for selection
        distinct_vals = engine.get_distinct_values(meta.name, limit=50)
        curr_selected = entry.get("value", [])
        if not isinstance(curr_selected, list):
            curr_selected = [curr_selected] if curr_selected else []

        selected = st.multiselect(
            "Seleziona valori:",
            options=distinct_vals,
            default=[v for v in curr_selected if v in distinct_vals],
            key=f"val_multi_{idx}",
        )
        return selected, None

    # Standard single value input
    val = st.text_input(
        "Valore",
        value=str(entry.get("value", "")),
        key=f"val_single_{idx}",
        placeholder="Inserisci valore...",
    )
    return val, None


def _is_filter_valid(op: FilterOperator, val: Any, val_to: Any) -> bool:
    if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        return True
    if op == FilterOperator.BETWEEN:
        return bool(str(val).strip() and str(val_to).strip())
    if op in (FilterOperator.IN_LIST, FilterOperator.NOT_IN_LIST):
        return isinstance(val, (list, tuple)) and len(val) > 0
    return bool(val is not None and str(val).strip())

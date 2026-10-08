"""
Dynamic Filter Battery UI component.
Adapts to any dataset schema, generating type-specific filter widgets
(text, numeric, categorical, date) and a global quick search bar.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.core.models import (
    ColumnMeta,
    DatasetSchema,
    DataType,
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
) -> tuple[list[FilterRule], str | None, list[str] | None]:
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
            import uuid
            first_col = schema.columns[0] if schema.columns else None
            first_col_name = first_col.name if first_col else ""
            default_op = FilterOperator.BETWEEN.value if (first_col and first_col.is_numeric()) else FilterOperator.CONTAINS.value
            st.session_state["filter_entries"].append({
                "id": uuid.uuid4().hex[:8],
                "column": first_col_name,
                "operator": default_op,
                "value": "",
                "value_to": "",
            })
            st.rerun()

    with col_btn_clear:
        if st.button("🧹 Rimuovi Tutti", use_container_width=True):
            st.session_state["filter_entries"] = []
            st.session_state["global_search_val"] = ""
            st.session_state["input_global_search"] = ""
            st.rerun()

    filter_rules: list[FilterRule] = []
    entries_to_delete: list[str] = []

    column_map: dict[str, ColumnMeta] = {c.name: c for c in schema.columns}
    col_display_options = [f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns]
    col_name_by_display = {f"{get_type_icon(c.data_type)} {c.name}": c.name for c in schema.columns}
    col_display_by_name = {c.name: f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns}

    # Render each filter row
    first_col_name = schema.columns[0].name if schema.columns else ""
    for entry in st.session_state["filter_entries"]:
        if "id" not in entry:
            import uuid
            entry["id"] = uuid.uuid4().hex[:8]
        entry_id = entry["id"]

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

        col_widget_key = f"col_sel_{entry_id}"
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
                    key=f"col_sel_{entry_id}",
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
                curr_op_val = entry.get("operator", allowed_ops[0].value)
                curr_op = FilterOperator(curr_op_val) if curr_op_val in [o.value for o in allowed_ops] else allowed_ops[0]

                sel_op = st.selectbox(
                    "Operatore",
                    options=allowed_ops,
                    format_func=_get_op_label,
                    index=allowed_ops.index(curr_op),
                    key=f"op_sel_{entry_id}",
                )
                entry["operator"] = sel_op.value

            # Input Values tailored to operator & type
            with f_cols[2]:
                val, val_to = _render_value_inputs(entry_id, entry, sel_op, meta, engine)
                entry["value"] = val
                entry["value_to"] = val_to

            # Delete button
            with f_cols[3]:
                st.write("")
                st.write("")
                if st.button("🗑️", key=f"del_btn_{entry_id}", help="Rimuovi filtro"):
                    entries_to_delete.append(entry_id)

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
        for del_id in entries_to_delete:
            st.session_state["filter_entries"] = [
                e for e in st.session_state["filter_entries"] if e.get("id") != del_id
            ]
            for prefix in ("col_sel_", "op_sel_", "val_single_", "val_min_", "val_max_", "val_multi_", "del_btn_"):
                k = f"{prefix}{del_id}"
                if k in st.session_state:
                    del st.session_state[k]
        st.rerun()
    # Reset pagination to page 1 when criteria change
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


def _get_allowed_operators(dtype: DataType) -> list[FilterOperator]:
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
    entry_id: str,
    entry: dict[str, Any],
    op: FilterOperator,
    meta: ColumnMeta,
    engine: DuckDBEngine,
) -> tuple[Any, Any]:
    if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        st.caption("Nessun parametro richiesto")
        return None, None

    if op == FilterOperator.BETWEEN:
        b_c1, b_c2 = st.columns(2)
        with b_c1:
            min_v = st.text_input(
                "Minimo",
                value=str(entry.get("value", "")),
                key=f"val_min_{entry_id}",
                placeholder="es. 1000",
            )
        with b_c2:
            max_v = st.text_input(
                "Massimo",
                value=str(entry.get("value_to", "")),
                key=f"val_max_{entry_id}",
                placeholder="es. 50000",
            )
        if min_v and max_v:
            try:
                if float(str(min_v).replace(",", ".")) > float(str(max_v).replace(",", ".")):
                    st.caption("ℹ️ Minimo superiore al massimo: l'intervallo verrà scambiato automaticamente")
            except ValueError:
                st.caption("⚠️ Inserire valori numerici validi")
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
            key=f"val_multi_{entry_id}",
        )
        return selected, None

    # Standard single value input
    val = st.text_input(
        "Valore",
        value=str(entry.get("value", "")),
        key=f"val_single_{entry_id}",
        placeholder="Inserisci valore...",
    )
    if op == FilterOperator.REGEX and val:
        import re
        try:
            re.compile(str(val).strip())
        except re.error:
            st.caption("⚠️ Espressione regolare non valida (verrà ignorata finché incompleta)")
    elif op in (FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE) and val:
        try:
            float(str(val).strip().replace(",", "."))
        except ValueError:
            st.caption("⚠️ Inserire un numero valido")

    return val, None


def _is_filter_valid(op: FilterOperator, val: Any, val_to: Any) -> bool:
    if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        return True
    if op == FilterOperator.REGEX:
        if not val or not str(val).strip():
            return False
        import re
        try:
            re.compile(str(val).strip())
            return True
        except re.error:
            return False
    if op == FilterOperator.BETWEEN:
        s_val, s_to = str(val).strip(), str(val_to).strip()
        if not (s_val and s_to):
            return False
        try:
            float(s_val.replace(",", "."))
            float(s_to.replace(",", "."))
            return True
        except ValueError:
            return False
    if op in (FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE):
        if val is None or not str(val).strip():
            return False
        try:
            float(str(val).strip().replace(",", "."))
            return True
        except ValueError:
            return False
    if op in (FilterOperator.IN_LIST, FilterOperator.NOT_IN_LIST):
        return isinstance(val, (list, tuple)) and len(val) > 0
    return bool(val is not None and str(val).strip())

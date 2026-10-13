"""
Dynamic Filter Battery UI component.
Adapts to any dataset schema, generating type-specific filter widgets
(text, numeric, categorical, date) and a global quick search bar.
Supports Notion / Airtable style nested filter groups.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import streamlit as st

from src.core.models import (
    BooleanOperator,
    ColumnMeta,
    DatasetSchema,
    DataType,
    FilterGroup,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


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
) -> tuple[
    list[FilterRule],
    str | None,
    list[str] | None,
    BooleanOperator,
    BooleanOperator,
    list[FilterGroup],
    BooleanOperator,
]:
    """
    Render global search bar and dynamic typed filter battery with Notion / Airtable style filter groups.
    Returns:
    (
        flat_filter_rules,
        global_search_term,
        global_search_columns,
        filter_logic,
        global_search_logic,
        filter_groups,
        filter_group_logic,
    )
    """
    if not schema or not schema.columns:
        return [], None, None, BooleanOperator.AND, BooleanOperator.AND, [], BooleanOperator.AND

    # Initialize filter groups state if not present
    if "filter_groups_state" not in st.session_state:
        legacy_entries = st.session_state.get("filter_entries", [])
        if legacy_entries:
            st.session_state["filter_groups_state"] = [
                {
                    "id": "grp_1",
                    "logic": st.session_state.get("filter_comb_logic_val", BooleanOperator.AND.value),
                    "entries": legacy_entries,
                }
            ]
        else:
            st.session_state["filter_groups_state"] = [
                {
                    "id": "grp_1",
                    "logic": BooleanOperator.AND.value,
                    "entries": [],
                }
            ]

    # 1. Quick Global Search Bar
    st.markdown("#### 🔍 Ricerca Rapida")
    col_search, col_cols = st.columns([3, 2])

    with col_search:
        global_search = st.text_input(
            "Cerca parola chiave o codice (es. Codice Fiscale, Denominazione...):",
            value=st.session_state.get("global_search_val", ""),
            placeholder="Digita termini separati da virgola (es. Roma, Milano)...",
            key="input_global_search",
        )
        st.session_state["global_search_val"] = global_search

        saved_gs_logic = st.session_state.get("global_search_logic_val", BooleanOperator.AND.value)
        gs_idx = 0 if saved_gs_logic != BooleanOperator.OR.value else 1
        selected_gs_logic = st.radio(
            "Corrispondenza termini ricerca rapida:",
            options=[BooleanOperator.AND.value, BooleanOperator.OR.value],
            format_func=lambda x: "Tutti i termini (AND)" if x == BooleanOperator.AND.value else "Almeno un termine (OR)",
            horizontal=True,
            index=gs_idx,
            key="radio_global_search_logic",
        )
        st.session_state["global_search_logic_val"] = selected_gs_logic
        global_search_logic = BooleanOperator(selected_gs_logic)

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

    # 2. Dynamic Filter Battery & Filter Groups
    st.markdown("#### ⚙️ Batteria Filtri Dinamici")

    first_col = schema.columns[0] if schema.columns else None
    first_col_name = first_col.name if first_col else ""
    default_op = (
        FilterOperator.BETWEEN.value
        if (first_col and first_col.is_numeric())
        else FilterOperator.CONTAINS.value
    )

    # Top Toolbar
    col_btn_add_f, col_btn_add_g, col_btn_clear = st.columns([2, 2.5, 3.5])

    with col_btn_add_f:
        if st.button("➕ Aggiungi Filtro", use_container_width=True, help="Aggiunge un criterio al primo gruppo"):
            if not st.session_state["filter_groups_state"]:
                st.session_state["filter_groups_state"] = [
                    {"id": f"grp_{uuid.uuid4().hex[:6]}", "logic": BooleanOperator.AND.value, "entries": []}
                ]
            st.session_state["filter_groups_state"][0]["entries"].append({
                "id": uuid.uuid4().hex[:8],
                "column": first_col_name,
                "operator": default_op,
                "value": "",
                "value_to": "",
                "term_logic": BooleanOperator.OR.value,
            })
            st.rerun()

    with col_btn_add_g:
        if st.button("📁 Aggiungi Gruppo", use_container_width=True, help="Crea un nuovo gruppo di filtri con logica indipendente"):
            new_grp_id = f"grp_{uuid.uuid4().hex[:6]}"
            st.session_state["filter_groups_state"].append({
                "id": new_grp_id,
                "logic": BooleanOperator.AND.value,
                "entries": [
                    {
                        "id": uuid.uuid4().hex[:8],
                        "column": first_col_name,
                        "operator": default_op,
                        "value": "",
                        "value_to": "",
                        "term_logic": BooleanOperator.OR.value,
                    }
                ],
            })
            st.rerun()

    with col_btn_clear:
        if st.button("🧹 Rimuovi Tutti", use_container_width=True):
            for k in list(st.session_state.keys()):
                if isinstance(k, str) and any(
                    k.startswith(pfx)
                    for pfx in (
                        "col_sel_",
                        "op_sel_",
                        "val_single_",
                        "val_min_",
                        "val_max_",
                        "val_multi_",
                        "term_logic_",
                        "del_btn_",
                        "radio_grp_logic_",
                        "del_grp_btn_",
                        "add_cond_btn_",
                    )
                ):
                    del st.session_state[k]
            st.session_state["filter_groups_state"] = [
                {
                    "id": "grp_1",
                    "logic": BooleanOperator.AND.value,
                    "entries": [],
                }
            ]
            st.session_state["filter_entries"] = []
            st.session_state["global_search_val"] = ""
            st.session_state["input_global_search"] = ""
            st.rerun()

    groups_count = len(st.session_state["filter_groups_state"])
    filter_group_logic = BooleanOperator.AND

    # Inter-group combination toggle if multiple groups exist
    if groups_count >= 2:
        saved_fg_comb = st.session_state.get("filter_groups_comb_logic", BooleanOperator.AND.value)
        fg_comb_idx = 0 if saved_fg_comb != BooleanOperator.OR.value else 1
        st.markdown("---")
        selected_fg_comb = st.radio(
            "Combina i gruppi di filtri tra loro con:",
            options=[BooleanOperator.AND.value, BooleanOperator.OR.value],
            format_func=lambda x: (
                "🔵 TUTTI i gruppi devono essere verificati (E / AND)"
                if x == BooleanOperator.AND.value
                else "🔀 ALMENO UN gruppo deve essere verificato (OPPURE / OR)"
            ),
            horizontal=True,
            index=fg_comb_idx,
            key="radio_filter_groups_comb_logic",
        )
        st.session_state["filter_groups_comb_logic"] = selected_fg_comb
        filter_group_logic = BooleanOperator(selected_fg_comb)

    column_map: dict[str, ColumnMeta] = {c.name: c for c in schema.columns}
    col_display_options = [f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns]
    col_name_by_display = {f"{get_type_icon(c.data_type)} {c.name}": c.name for c in schema.columns}
    col_display_by_name = {c.name: f"{get_type_icon(c.data_type)} {c.name}" for c in schema.columns}

    groups_to_delete: list[str] = []
    entries_to_delete: list[tuple[str, str]] = []  # (group_id, entry_id)

    compiled_filter_groups: list[FilterGroup] = []
    flat_filter_rules: list[FilterRule] = []

    # Render each filter group
    for grp_idx, grp in enumerate(st.session_state["filter_groups_state"]):
        grp_id = grp["id"]
        entries = grp.get("entries", [])

        # Inter-group connector banner
        if grp_idx > 0:
            if filter_group_logic == BooleanOperator.AND:
                st.markdown(
                    "<div style='text-align:center; padding: 6px; margin: 12px 0 8px 0; "
                    "background: rgba(59, 130, 246, 0.08); border: 1px dashed rgba(59, 130, 246, 0.4); "
                    "border-radius: 6px; font-weight: 700; color: #2563eb; font-size: 0.82rem;'>"
                    "🔗 E (AND) TRA I GRUPPI DI FILTRI"
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='text-align:center; padding: 6px; margin: 12px 0 8px 0; "
                    "background: rgba(245, 158, 11, 0.08); border: 1px dashed rgba(245, 158, 11, 0.4); "
                    "border-radius: 6px; font-weight: 700; color: #d97706; font-size: 0.82rem;'>"
                    "🔀 OPPURE (OR) TRA I GRUPPI DI FILTRI"
                    "</div>",
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            # Group Header Card
            h_col1, h_col2, h_col3 = st.columns([2.2, 5.8, 2.0])
            with h_col1:
                st.markdown(f"##### 📁 Gruppo {grp_idx + 1}")

            with h_col2:
                if len(entries) >= 2:
                    saved_grp_logic = grp.get("logic", BooleanOperator.AND.value)
                    gl_idx = 0 if saved_grp_logic != BooleanOperator.OR.value else 1
                    chosen_gl = st.radio(
                        "Condizioni in questo gruppo:",
                        options=[BooleanOperator.AND.value, BooleanOperator.OR.value],
                        format_func=lambda x: (
                            "Tutte le condizioni (E / AND)"
                            if x == BooleanOperator.AND.value
                            else "Almeno una condizione (O / OR)"
                        ),
                        horizontal=True,
                        index=gl_idx,
                        key=f"radio_grp_logic_{grp_id}",
                    )
                    grp["logic"] = chosen_gl
                else:
                    grp["logic"] = grp.get("logic", BooleanOperator.AND.value)

            with h_col3:
                if groups_count > 1 and st.button("🗑️ Elimina Gruppo", key=f"del_grp_btn_{grp_id}", use_container_width=True):
                    groups_to_delete.append(grp_id)

            group_rules: list[FilterRule] = []

            # Render filter rows in this group
            for e_idx, entry in enumerate(entries):
                if "id" not in entry:
                    entry["id"] = uuid.uuid4().hex[:8]
                entry_id = entry["id"]

                # Inter-rule connector badge inside group
                if e_idx > 0:
                    grp_logic_val = grp.get("logic", BooleanOperator.AND.value)
                    conn_text = "— E (AND) —" if grp_logic_val == BooleanOperator.AND.value else "— OPPURE (OR) —"
                    conn_color = "#3b82f6" if grp_logic_val == BooleanOperator.AND.value else "#f59e0b"
                    st.markdown(
                        f"<div style='text-align: center; color: {conn_color}; font-weight: 600; "
                        f"font-size: 0.8rem; margin: 0 0 6px 0;'>"
                        f"{conn_text}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

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
                        new_meta = column_map[selected_col_name]
                        entry["operator"] = (
                            FilterOperator.BETWEEN.value
                            if new_meta.is_numeric()
                            else FilterOperator.CONTAINS.value
                        )
                        entry["value"] = ""
                        st.rerun()

                # Select Operator tailored to type
                with f_cols[1]:
                    allowed_ops = _get_allowed_operators(dtype)
                    curr_op_val = entry.get("operator", allowed_ops[0].value)
                    curr_op = (
                        FilterOperator(curr_op_val)
                        if curr_op_val in [o.value for o in allowed_ops]
                        else allowed_ops[0]
                    )

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
                    if st.button("🗑️", key=f"del_btn_{entry_id}", help="Rimuovi questo filtro"):
                        entries_to_delete.append((grp_id, entry_id))

                # Build FilterRule object if valid
                if _is_filter_valid(sel_op, val, val_to):
                    term_logic_val = entry.get("term_logic", BooleanOperator.OR.value)
                    term_logic_enum = (
                        BooleanOperator(term_logic_val)
                        if sel_op in (FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS)
                        else BooleanOperator.AND
                    )
                    rule = FilterRule(
                        column=selected_col_name,
                        operator=sel_op,
                        value=val,
                        value_to=val_to,
                        term_logic=term_logic_enum,
                    )
                    group_rules.append(rule)
                    flat_filter_rules.append(rule)

            # Bottom of group: Add condition button
            btn_add_cond_col, _ = st.columns([3.5, 6.5])
            with btn_add_cond_col:
                if st.button(
                    f"➕ Aggiungi condizione a Gruppo {grp_idx + 1}",
                    key=f"add_cond_btn_{grp_id}",
                    use_container_width=True,
                ):
                    grp["entries"].append({
                        "id": uuid.uuid4().hex[:8],
                        "column": first_col_name,
                        "operator": default_op,
                        "value": "",
                        "value_to": "",
                        "term_logic": BooleanOperator.OR.value,
                    })
                    st.rerun()

            grp_logic_enum = BooleanOperator(grp.get("logic", BooleanOperator.AND.value))
            compiled_filter_groups.append(
                FilterGroup(id=grp_id, rules=group_rules, logic=grp_logic_enum)
            )

    # Process deletions
    if groups_to_delete:
        st.session_state["filter_groups_state"] = [
            g for g in st.session_state["filter_groups_state"] if g["id"] not in groups_to_delete
        ]
        if not st.session_state["filter_groups_state"]:
            st.session_state["filter_groups_state"] = [
                {"id": "grp_1", "logic": BooleanOperator.AND.value, "entries": []}
            ]
        st.rerun()

    if entries_to_delete:
        for grp_id, entry_id in entries_to_delete:
            for grp in st.session_state["filter_groups_state"]:
                if grp["id"] == grp_id:
                    grp["entries"] = [e for e in grp["entries"] if e.get("id") != entry_id]
            for prefix in (
                "col_sel_",
                "op_sel_",
                "val_single_",
                "val_min_",
                "val_max_",
                "val_multi_",
                "term_logic_",
                "del_btn_",
            ):
                k = f"{prefix}{entry_id}"
                if k in st.session_state:
                    del st.session_state[k]
        st.rerun()

    # Synchronize legacy flat entries in session state
    st.session_state["filter_entries"] = [
        e for grp in st.session_state["filter_groups_state"] for e in grp.get("entries", [])
    ]

    # Overall filter logic
    overall_filter_logic = (
        compiled_filter_groups[0].logic
        if len(compiled_filter_groups) == 1
        else filter_group_logic
    )

    # Real-Time Human-Readable Preview Banner
    preview_spec = QuerySpec(
        filters=flat_filter_rules,
        filter_groups=compiled_filter_groups,
        filter_group_logic=filter_group_logic,
        global_search=global_search.strip() or None,
        global_search_columns=search_cols or None,
        global_search_logic=global_search_logic,
    )
    human_summary = QueryBuilder.build_human_readable_filter_summary(preview_spec)
    if human_summary:
        st.info(f"🎯 **Criterio applicato**: `{human_summary}`")

    # Reset pagination to page 1 when criteria change
    search_sig = (
        str(global_search.strip() if global_search else ""),
        global_search_logic.value,
        tuple(sorted(search_cols or [])),
        overall_filter_logic.value,
        filter_group_logic.value,
        tuple(
            (
                g.id,
                g.logic.value,
                tuple((r.column, r.operator.value, str(r.value), str(r.value_to), r.term_logic.value) for r in g.rules),
            )
            for g in compiled_filter_groups
        ),
    )
    if st.session_state.get("_prev_filter_signature") != search_sig:
        st.session_state["_prev_filter_signature"] = search_sig
        st.session_state["current_page"] = 1
        if "page_num_input" in st.session_state:
            st.session_state["page_num_input"] = 1

    return (
        flat_filter_rules,
        global_search.strip() or None,
        search_cols or None,
        overall_filter_logic,
        global_search_logic,
        compiled_filter_groups,
        filter_group_logic,
    )


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

    # Standard single or multi-value text input
    is_contains_op = op in (FilterOperator.CONTAINS, FilterOperator.NOT_CONTAINS)
    label = "Valore (separa con virgola per più termini)" if is_contains_op else "Valore"
    placeholder = "es. termine1, termine2..." if is_contains_op else "Inserisci valore..."
    val = st.text_input(
        label,
        value=str(entry.get("value", "")),
        key=f"val_single_{entry_id}",
        placeholder=placeholder,
    )

    if is_contains_op:
        saved_t_logic = entry.get("term_logic", BooleanOperator.OR.value)
        t_idx = 0 if saved_t_logic == BooleanOperator.OR.value else 1
        chosen_t_logic = st.radio(
            "Corrispondenza termini:",
            options=[BooleanOperator.OR.value, BooleanOperator.AND.value],
            format_func=lambda x: (
                "Almeno uno (OR) — Consigliato per elenchi"
                if x == BooleanOperator.OR.value
                else "Tutti i termini (AND)"
            ),
            horizontal=True,
            index=t_idx,
            key=f"term_logic_{entry_id}",
        )
        entry["term_logic"] = chosen_t_logic

    if op == FilterOperator.REGEX and val:
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

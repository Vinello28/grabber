"""
Aggregations and Group By UI component.
Enables ad-hoc multi-column grouping, distinct counts, and metric summarization.
"""

from __future__ import annotations
from typing import List, Optional
import pandas as pd
import streamlit as st

from src.core.models import (
    AggregationFunc,
    AggregationRule,
    ColumnMeta,
    DatasetSchema,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine


def render_aggregations(
    schema: DatasetSchema,
    engine: DuckDBEngine,
    filters: List[FilterRule],
    global_search: Optional[str],
    global_search_cols: Optional[List[str]],
):
    """Render interactive Group By, metrics and distinct analysis tab."""
    st.markdown("#### 📊 Raggruppamenti & Analisi Aggregata (Group By / Distinct)")
    st.caption("Le aggregazioni vengono calcolate in streaming considerando i filtri attualmente attivi.")

    all_cols = schema.column_names
    numeric_cols = [c.name for c in schema.columns if c.is_numeric()]

    tab_group, tab_distinct = st.tabs(["Raggruppamento Multi-Colonna", "Valori Distinti (Distinct)"])

    # 1. GROUP BY TAB
    with tab_group:
        col_g1, col_g2 = st.columns([1, 1])

        default_group = [all_cols[0]] if all_cols else []
        if "agg_group_by_cols" in st.session_state:
            valid_grp = [c for c in st.session_state["agg_group_by_cols"] if c in all_cols]
            st.session_state["agg_group_by_cols"] = valid_grp if valid_grp else default_group

        with col_g1:
            group_cols = st.multiselect(
                "Colonne di Raggruppamento (Group By):",
                options=all_cols,
                default=default_group,
                key="agg_group_by_cols",
            )

        with col_g2:
            limit_rows = st.number_input(
                "Numero massimo di gruppi:",
                min_value=5,
                max_value=10000,
                value=50,
                step=10,
                key="agg_limit_input",
            )

        st.markdown("##### Metriche da Calcolare")
        metric_c1, metric_c2, metric_c3 = st.columns(3)

        sum_options = ["(Nessuna)"] + numeric_cols
        if "agg_sum_col" in st.session_state and st.session_state["agg_sum_col"] not in sum_options:
            st.session_state["agg_sum_col"] = "(Nessuna)"

        dist_options = ["(Nessuna)"] + all_cols
        if "agg_distinct_col" in st.session_state and st.session_state["agg_distinct_col"] not in dist_options:
            st.session_state["agg_distinct_col"] = "(Nessuna)"

        with metric_c1:
            add_count = st.checkbox("Conteggio record (COUNT)", value=True, key="agg_chk_count")
        with metric_c2:
            sum_col = st.selectbox(
                "Somma (SUM) su colonna:",
                options=sum_options,
                index=0,
                key="agg_sum_col",
            )
        with metric_c3:
            distinct_col = st.selectbox(
                "Valori unici (COUNT DISTINCT) su colonna:",
                options=dist_options,
                index=0,
                key="agg_distinct_col",
            )

        if st.button("🚀 Esegui Raggruppamento", type="primary", use_container_width=True):
            if not group_cols:
                st.warning("Seleziona almeno una colonna di raggruppamento.")
            else:
                aggs: List[AggregationRule] = []
                if add_count:
                    aggs.append(AggregationRule(column="*", func=AggregationFunc.COUNT, alias="conteggio"))
                if sum_col != "(Nessuna)":
                    aggs.append(AggregationRule(column=sum_col, func=AggregationFunc.SUM, alias=f"somma_{sum_col}"))
                if distinct_col != "(Nessuna)":
                    aggs.append(AggregationRule(column=distinct_col, func=AggregationFunc.COUNT_DISTINCT, alias=f"unici_{distinct_col}"))

                spec = QuerySpec(
                    filters=filters,
                    global_search=global_search,
                    global_search_columns=global_search_cols,
                    group_by_columns=group_cols,
                    aggregations=aggs,
                    limit=int(limit_rows),
                )

                with st.spinner("Calcolo aggregazioni out-of-core in corso..."):
                    try:
                        res = engine.execute_query(spec)
                        st.success(f"Calcolo completato in {res.execution_time_seconds:.3f} secondi!")

                        if res.rows:
                            df_agg = pd.DataFrame(res.rows, columns=res.columns)
                            st.dataframe(df_agg, use_container_width=True)

                            # Visual chart if 1 group column and at least 1 numeric metric
                            if len(group_cols) == 1 and len(res.columns) > 1:
                                primary_metric = res.columns[1]
                                chart_df = df_agg.set_index(group_cols[0])[[primary_metric]].head(20)
                                st.bar_chart(chart_df)
                        else:
                            st.info("Nessun dato per i parametri specificati.")
                    except Exception as e:
                        st.error(f"Errore durante l'aggregazione: {e}")

    # 2. DISTINCT TAB
    with tab_distinct:
        if "distinct_col_sel" in st.session_state and st.session_state["distinct_col_sel"] not in all_cols:
            if all_cols:
                st.session_state["distinct_col_sel"] = all_cols[0]
            else:
                del st.session_state["distinct_col_sel"]

        sel_dist_col = st.selectbox("Seleziona colonna per visualizzare valori distinti:", options=all_cols, key="distinct_col_sel")
        max_dist_vals = st.slider("Numero massimo di valori da recuperare:", min_value=10, max_value=500, value=100)

        if st.button("🔍 Mostra Valori Distinti", key="btn_fetch_distinct"):
            with st.spinner("Ricerca valori distinti..."):
                spec = QuerySpec(
                    filters=filters,
                    global_search=global_search,
                    global_search_columns=global_search_cols,
                    group_by_columns=[sel_dist_col],
                    aggregations=[AggregationRule(column="*", func=AggregationFunc.COUNT, alias="frequenza")],
                    limit=max_dist_vals,
                )
                try:
                    res = engine.execute_query(spec)
                    if res.rows:
                        df_dist = pd.DataFrame(res.rows, columns=[sel_dist_col, "Frequenza"])
                        st.dataframe(df_dist, use_container_width=True)
                    else:
                        st.info("Nessun valore trovato.")
                except Exception as e:
                    st.error(f"Errore: {e}")

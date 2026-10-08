"""
Grabber - Big Data Analytical Query Engine GUI
Cross-platform Streamlit application designed for out-of-core big data exploration (70+ GB)
with dynamic dataset-agnostic filter battery, aggregations, and streaming export.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
root_dir = str(Path(__file__).resolve().parent.parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import pandas as pd
import streamlit as st

from src.engine.duckdb_engine import DuckDBEngine
from src.ui.components.system_stats import render_system_stats
from src.ui.components.dataset_selector import render_dataset_selector
from src.ui.components.filter_battery import render_filter_battery, get_type_icon
from src.ui.components.data_viewer import render_data_viewer
from src.ui.components.aggregations import render_aggregations
from src.ui.components.export_panel import render_export_panel
from src.ui.components.update_checker import render_update_checker
from src.ui.state_manager import reset_dataset_ui_state


st.set_page_config(
    page_title="Grabber | Big Data Analytical Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_engine() -> DuckDBEngine:
    """Instantiate and cache DuckDB analytical engine across interactions."""
    return DuckDBEngine()


def main():
    engine = get_engine()

    # Sidebar: System Stats & Dataset Loader
    with st.sidebar:
        st.title("⚡ Grabber Engine")
        st.caption("Motore Analitico Out-of-Core per Big Data (>70 GB)")
        st.divider()

        render_system_stats()
        schema = render_dataset_selector(engine)
        render_update_checker()

    # Main Area
    if not schema:
        _render_welcome_screen()
        return

    # Ensure UI session state matches the active schema path
    if st.session_state.get("active_dataset_path") != schema.source_path:
        reset_dataset_ui_state()
        st.session_state["active_dataset_path"] = schema.source_path

    # Double check that the database view is ready
    try:
        engine.ensure_view_exists()
    except Exception:
        try:
            schema = engine.connect_dataset(schema.source_path)
        except Exception:
            pass

    # Dataset Header Banner
    st.subheader(f"📊 Dataset: `{Path(schema.source_path).name}`")
    badge_cols = st.columns(4)
    with badge_cols[0]:
        st.metric("Formato", schema.source_format.upper())
    with badge_cols[1]:
        st.metric("File Inclusi", f"{schema.file_count}")
    with badge_cols[2]:
        if schema.total_size_bytes:
            gb = schema.total_size_bytes / (1024 ** 3)
            st.metric("Dimensione Totale", f"{gb:.2f} GB" if gb >= 1.0 else f"{schema.total_size_bytes / (1024**2):.1f} MB")
        else:
            st.metric("Dimensione", "N/D")
    with badge_cols[3]:
        rows_str = f"{schema.row_count_estimate:,}" if schema.row_count_estimate else "In calcolo..."
        st.metric("Record Totali", rows_str)

    st.divider()

    # Dynamic Filter Battery & Global Search
    filters, global_search, search_cols = render_filter_battery(schema, engine)

    st.divider()

    # Operational Tabs
    tab_viewer, tab_aggs, tab_export, tab_schema = st.tabs([
        "📋 Visualizzatore Dati",
        "📊 Raggruppamenti & Distinct",
        "💾 Esportazione Streaming",
        "ℹ️ Schema & Metadati Colonne",
    ])

    with tab_viewer:
        render_data_viewer(schema, engine, filters, global_search, search_cols)

    with tab_aggs:
        render_aggregations(schema, engine, filters, global_search, search_cols)

    with tab_export:
        render_export_panel(schema, engine, filters, global_search, search_cols)

    with tab_schema:
        _render_schema_tab(schema)


def _render_welcome_screen():
    st.title("🚀 Benvenuto in Grabber")
    st.markdown("""
    **Grabber** è un'applicazione progettata per eseguire query ad elevate prestazioni su **dataset di grandi dimensioni (>70 GB)** 
    anche su workstation con **meno di 16 GB di RAM**.

    ### ✨ Caratteristiche Principali:
    - **Dataset-Agnostic**: Rileva automaticamente colonne e tipologie di qualsiasi dataset (.csv, .parquet, .xml).
    - **Memoria Costante & Out-of-Core**: Utilizza un motore vettorializzato DuckDB con spillover automatico su disco.
    - **Batteria di Filtri Dinamica**: Adatta gli operatori di filtraggio al tipo di dato (testuale, numerico, categorico).
    - **Raggruppamenti & Distinct**: Esegue calcoli aggregati su decine di milioni di record in pochi secondi.
    - **Esportazione Diretta**: Esporta i dati filtrati in formato CSV o Parquet in streaming a memoria zero.

    ---
    👈 **Per iniziare**, seleziona un percorso nella barra laterale o clicca su una delle scorciatoie predefinite.
    """)


def _render_schema_tab(schema):
    st.markdown("#### ℹ️ Colonne e Tipi Rilevati nel Dataset")
    rows = []
    for c in schema.columns:
        rows.append({
            "Icona": get_type_icon(c.data_type),
            "Nome Colonna": c.name,
            "Tipo Logico": c.data_type.value.upper(),
            "Tipo Nativo": c.native_type,
            "Esempi di Valore": ", ".join(str(s) for s in c.sample_values[:4]),
        })
    df_schema = pd.DataFrame(rows)
    st.dataframe(df_schema, use_container_width=True, height=500)


if __name__ == "__main__":
    main()

"""
Dataset selector UI component.
Allows users to load CSV, Parquet, or XML datasets from local paths or presets.
"""

import os
from pathlib import Path
import streamlit as st
from src.engine.duckdb_engine import DuckDBEngine
from src.core.models import DatasetSchema
from src.ui.file_picker import pick_system_folder, pick_system_file
from src.ui.state_manager import reset_dataset_ui_state


def render_dataset_selector(engine: DuckDBEngine) -> DatasetSchema | None:
    """Render dataset loader, native file/folder pickers, and handle connection state."""
    st.sidebar.markdown("### 📂 Selezione Dataset")

    # Native OS File & Folder Pickers
    st.sidebar.caption("Seleziona da Esplora Risorse / Finder:")
    picker_col1, picker_col2 = st.sidebar.columns(2)
    with picker_col1:
        if picker_col1.button("📁 Cartella", key="btn_pick_folder", use_container_width=True, help="Apri finestra nativa per selezionare una cartella"):
            selected_folder = pick_system_folder("Seleziona la cartella del dataset")
            if selected_folder:
                st.session_state["dataset_path"] = selected_folder
                st.session_state["trigger_load"] = True
                st.rerun()

    with picker_col2:
        if picker_col2.button("📄 File", key="btn_pick_file", use_container_width=True, help="Apri finestra nativa per selezionare un file"):
            selected_file = pick_system_file("Seleziona il file del dataset")
            if selected_file:
                st.session_state["dataset_path"] = selected_file
                st.session_state["trigger_load"] = True
                st.rerun()

    # Preset quick-load buttons
    presets = {
        "CSV Test (13.5 GB)": "data/test1",
        "XML Annihilation (62 GB)": "data/annihilation_test",
    }

    st.sidebar.caption("Scorciatoie veloci:")
    preset_cols = st.sidebar.columns(len(presets))
    for i, (name, path) in enumerate(presets.items()):
        if os.path.exists(path):
            if preset_cols[i].button(name, key=f"preset_{i}", use_container_width=True):
                st.session_state["dataset_path"] = path
                st.session_state["trigger_load"] = True

    current_path = st.session_state.get("dataset_path", "data/test1")
    path_input = st.sidebar.text_input(
        "Percorso file o cartella:",
        value=current_path,
        help="Inserisci il percorso assoluto o relativo di un file (.csv, .parquet, .xml) o cartella.",
    )

    load_clicked = st.sidebar.button("Carica Dataset", type="primary", use_container_width=True)

    if load_clicked or st.session_state.get("trigger_load", False):
        st.session_state["trigger_load"] = False
        st.session_state["dataset_path"] = path_input

        with st.sidebar.status("Connessione e scansione schema in corso...", expanded=True) as status:
            try:
                reset_dataset_ui_state()
                schema = engine.connect_dataset(path_input)
                st.session_state["schema"] = schema
                st.session_state["active_dataset_path"] = path_input
                status.update(label="Dataset caricato con successo!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Errore nel caricamento", state="error", expanded=True)
                st.sidebar.error(f"Errore: {str(e)}")
                return None

    # Guarantee in-memory DuckDB view is synchronized if session state has a dataset
    if current_path and (not engine.has_active_view() or engine.current_dataset_path != current_path):
        if os.path.exists(current_path):
            try:
                if st.session_state.get("active_dataset_path") != current_path:
                    reset_dataset_ui_state()
                schema = engine.connect_dataset(current_path)
                st.session_state["schema"] = schema
                st.session_state["active_dataset_path"] = current_path
            except Exception:
                pass

    schema: DatasetSchema | None = st.session_state.get("schema")

    if schema:
        # Check XML indexing status
        if schema.source_format == "xml" and schema.table_identifier == "xml_source":
            st.sidebar.warning(
                "⚠️ Dataset XML rilevato. Per abilitare query analitiche interattive ad alte prestazioni, "
                "è consigliata l'indicizzazione streaming in cache Parquet."
            )
            if st.sidebar.button("⚡ Indicizza XML in Parquet (Streaming)", type="primary"):
                progress_bar = st.sidebar.progress(0.0)
                status_text = st.sidebar.empty()

                def on_progress(frac: float, bytes_done: int, rows_done: int):
                    progress_bar.progress(frac)
                    mb_done = bytes_done / (1024 * 1024)
                    status_text.caption(f"Elaborati: {mb_done:.1f} MB | {rows_done:,} record")

                with st.spinner("Conversione streaming in corso..."):
                    engine.index_xml_dataset(progress_callback=on_progress)
                st.sidebar.success("Indicizzazione completata!")
                st.rerun()

        # Display metadata card
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Formato:** `{schema.source_format.upper()}`")
        st.sidebar.markdown(f"**File totali:** `{schema.file_count}`")
        if schema.total_size_bytes:
            size_gb = schema.total_size_bytes / (1024 ** 3)
            size_mb = schema.total_size_bytes / (1024 ** 2)
            size_str = f"{size_gb:.2f} GB" if size_gb >= 1.0 else f"{size_mb:.1f} MB"
            st.sidebar.markdown(f"**Dimensione su disco:** `{size_str}`")
        if schema.row_count_estimate:
            st.sidebar.markdown(f"**Righe stimate:** `{schema.row_count_estimate:,}`")
        st.sidebar.markdown(f"**Colonne:** `{len(schema.columns)}`")

    st.sidebar.divider()
    return schema

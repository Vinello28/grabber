"""
Dataset selector UI component.
Allows users to load CSV, Parquet, or XML datasets from local paths or presets.
"""

import os
import sys

import streamlit as st

from src.adapters.detector import DatasetDetector
from src.core.models import DatasetSchema
from src.engine.duckdb_engine import DuckDBEngine
from src.ui.file_picker import pick_system_file, pick_system_folder
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

    # Quick test presets (development mode only, excluded in production)
    is_prod = getattr(sys, "frozen", False) or os.getenv("GRABBER_ENV", "").lower() == "production"
    if not is_prod:
        presets = {
            "Test CSV": "data/test1",
            "Test XML": "data/annihilation_test",
        }
        available_presets = {k: v for k, v in presets.items() if os.path.exists(v)}
        if available_presets:
            st.sidebar.caption("Scorciatoie test (Dev):")
            preset_cols = st.sidebar.columns(len(available_presets))
            for i, (name, path) in enumerate(available_presets.items()):
                if preset_cols[i].button(name, key=f"preset_{i}", use_container_width=True):
                    st.session_state["dataset_path"] = path
                    st.session_state["trigger_load"] = True

    default_path = "" if is_prod else ("data/test1" if os.path.exists("data/test1") else "")
    current_path = st.session_state.get("dataset_path", default_path)
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
                loaded_schema = engine.connect_dataset(path_input)
                st.session_state["schema"] = loaded_schema
                st.session_state["active_dataset_path"] = path_input
                status.update(label="Dataset caricato con successo!", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Errore nel caricamento", state="error", expanded=True)
                st.sidebar.error(f"Errore: {e!s}")
                st.session_state["schema"] = None
                st.session_state["active_dataset_path"] = None
                return None

    # Sync in-memory DuckDB view if session state has a dataset
    if current_path and (not engine.has_active_view() or engine.current_dataset_path != current_path) and os.path.exists(current_path):
        try:
            if st.session_state.get("active_dataset_path") != current_path:
                reset_dataset_ui_state()
            synced_schema = engine.connect_dataset(current_path)
            st.session_state["schema"] = synced_schema
            st.session_state["active_dataset_path"] = current_path
        except Exception:
            pass

    active_schema: DatasetSchema | None = st.session_state.get("schema")

    if active_schema:
        # Check XML indexing status
        if active_schema.source_format == "xml":
            analysis = DatasetDetector.analyze_path(active_schema.source_path)
            total_xml_files = len(analysis["files"])
            cache_path = engine.xml_adapter.get_cache_path(analysis["files"])

            existing_parts = set()
            if cache_path.exists():
                for pf in cache_path.glob("**/*.parquet"):
                    try:
                        part_num = int(pf.name.split("_")[1])
                        existing_parts.add(part_num)
                    except (IndexError, ValueError):
                        pass

            indexed_count = len(existing_parts)
            is_fully_indexed = (indexed_count >= total_xml_files > 0)

            if not is_fully_indexed:
                if indexed_count > 0:
                    st.sidebar.warning(
                        f"⚠️ **Indicizzazione parziale**: trovati {indexed_count} su {total_xml_files} file convertiti. "
                        "Riavvia per completare l'indicizzazione su tutti i file."
                    )
                    btn_label = f"⚡ Riavvia / Completa Indicizzazione ({indexed_count}/{total_xml_files} file)"
                else:
                    st.sidebar.warning(
                        "⚠️ **Dataset XML non indicizzato**. Per abilitare query analitiche interattive ad alte prestazioni, "
                        "è richiesta l'indicizzazione streaming in cache Parquet."
                    )
                    btn_label = "⚡ Indicizza XML in Parquet (Multi-Core)"

                if st.sidebar.button(btn_label, type="primary", use_container_width=True):
                    _run_xml_indexing(engine, active_schema, clean_cache=(indexed_count > 0))
            else:
                st.sidebar.success(f"⚡ **Cache Parquet attiva**: {total_xml_files}/{total_xml_files} file indicizzati.")
                with st.sidebar.expander("🔄 Re-indicizza / Aggiorna Cache XML", expanded=False):
                    st.caption("Usa questo pulsante per rigenerare la cache Parquet da zero.")
                    if st.button("Riavvia indicizzazione XML da zero", key="btn_reindex_xml", use_container_width=True):
                        _run_xml_indexing(engine, active_schema, clean_cache=True)

        # Display metadata card
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Formato:** `{active_schema.source_format.upper()}`")
        st.sidebar.markdown(f"**File totali:** `{active_schema.file_count}`")
        if active_schema.total_size_bytes:
            size_gb = active_schema.total_size_bytes / (1024 ** 3)
            size_mb = active_schema.total_size_bytes / (1024 ** 2)
            size_str = f"{size_gb:.2f} GB" if size_gb >= 1.0 else f"{size_mb:.1f} MB"
            st.sidebar.markdown(f"**Dimensione su disco:** `{size_str}`")
        if active_schema.row_count_estimate:
            st.sidebar.markdown(f"**Righe stimate:** `{active_schema.row_count_estimate:,}`")
        st.sidebar.markdown(f"**Colonne:** `{len(active_schema.columns)}`")

    st.sidebar.divider()
    return active_schema


def _run_xml_indexing(engine: DuckDBEngine, schema: DatasetSchema, clean_cache: bool = False) -> None:
    """Run parallel streaming XML conversion with real-time UI progress updates."""
    progress_bar = st.sidebar.progress(0.0)
    status_text = st.sidebar.empty()
    total_mb = (schema.total_size_bytes or 0) / (1024 * 1024)

    def on_progress(frac: float, bytes_done: int, rows_done: int):
        progress_bar.progress(min(1.0, frac))
        mb_done = bytes_done / (1024 * 1024)
        if total_mb > 0:
            status_text.caption(
                f"Elaborati: {mb_done:.1f} MB di {total_mb:.1f} MB ({frac * 100:.1f}%) | {rows_done:,} record"
            )
        else:
            status_text.caption(f"Elaborati: {mb_done:.1f} MB | {rows_done:,} record")

    with st.spinner("Conversione streaming multi-core in corso..."):
        engine.index_xml_dataset(progress_callback=on_progress, clean_cache=clean_cache)
    st.sidebar.success("Indicizzazione completata con successo!")
    st.rerun()

"""
Export Panel UI component.
Enables streaming out-of-core export of filtered datasets directly to disk or browser.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.core.models import DatasetSchema, FilterRule, QuerySpec
from src.engine.duckdb_engine import DuckDBEngine


def render_export_panel(
    schema: DatasetSchema,
    engine: DuckDBEngine,
    filters: list[FilterRule],
    global_search: str | None,
    global_search_cols: list[str] | None,
):
    """Render export modal/section for filtered dataset."""
    st.markdown("#### 💾 Esportazione Dati Filtrati")
    st.caption("L'esportazione avviene in streaming diretto su disco.")

    # Calculate count of matching rows
    spec = QuerySpec(
        filters=filters,
        global_search=global_search,
        global_search_columns=global_search_cols,
    )

    with st.spinner("Calcolo righe corrispondenti per l'esportazione..."):
        try:
            total_matching = engine.count_matching_rows(spec)
        except Exception as e:
            if schema.source_format == "xml" and engine.current_sql_source is None:
                st.info(
                    "ℹ️ **Dataset XML non ancora indicizzato**: per esportare i dati filtrati, "
                    "avvia la conversione streaming cliccando su **'⚡ Indicizza XML in Parquet'** nella barra laterale."
                )
            else:
                st.error(f"Errore: {e}")
            return

    st.success(f"🎯 **{total_matching:,} record** selezionati e pronti per l'esportazione.")

    if total_matching == 0:
        st.warning("Nessun record corrisponde ai filtri selezionati. Modifica i filtri per esportare i dati.")
        return

    exp_c1, exp_c2 = st.columns([1, 2])

    with exp_c1:
        export_fmt = st.selectbox(
            "Formato di esportazione:",
            options=["CSV", "Parquet", "JSON"],
            index=0,
            key="export_fmt_select",
        )

    ext = export_fmt.lower()
    default_filename = f"export_filtrato_{Path(schema.source_path).stem}.{ext}"

    # Sync file extension when export format selectbox changes
    prev_fmt = st.session_state.get("_prev_export_fmt")
    if prev_fmt != export_fmt:
        st.session_state["_prev_export_fmt"] = export_fmt
        if "export_path_input" in st.session_state:
            old_p = Path(st.session_state["export_path_input"])
            st.session_state["export_path_input"] = str(old_p.with_suffix(f".{ext}"))

    with exp_c2:
        export_path = st.text_input(
            "Percorso di salvataggio file:",
            value=os.path.join(os.getcwd(), "exports", default_filename),
            key="export_path_input",
        )

    if st.button("🚀 Avvia Esportazione Streaming su Disco", type="primary", use_container_width=True):
        progress_bar = st.progress(0.0)
        status_msg = st.empty()

        with st.spinner(f"Esportazione streaming in corso in {export_fmt}..."):
            try:
                Path(export_path).parent.mkdir(parents=True, exist_ok=True)
                def _on_export_progress(f: float) -> None:
                    progress_bar.progress(f)

                rows_done = engine.export_query(
                    spec,
                    export_path,
                    export_format=ext,
                    progress_callback=_on_export_progress,
                )
                file_size_mb = os.path.getsize(export_path) / (1024 * 1024)
                st.session_state["last_export_path"] = export_path
                st.session_state["last_export_rows"] = rows_done
                st.session_state["last_export_size_mb"] = file_size_mb
                st.session_state["last_export_fmt"] = ext
                status_msg.empty()
            except Exception as e:
                status_msg.error(f"Errore durante l'esportazione: {e}")

    # Render persistent export result and browser download button across reruns
    last_path = st.session_state.get("last_export_path")
    if last_path and os.path.exists(last_path):
        last_rows = st.session_state.get("last_export_rows", 0)
        last_size_mb = st.session_state.get("last_export_size_mb", 0.0)
        last_fmt = st.session_state.get("last_export_fmt", "csv")
        st.success(
            f"✅ Esportazione completata con successo!  \n"
            f"**File:** `{last_path}`  \n"
            f"**Righe:** `{last_rows:,}`  \n"
            f"**Dimensione:** `{last_size_mb:.2f} MB`"
        )
        if last_size_mb <= 150.0:
            with open(last_path, "rb") as f:
                st.download_button(
                    label=f"📥 Scarica direttamente nel browser ({last_size_mb:.1f} MB)",
                    data=f.read(),
                    file_name=Path(last_path).name,
                    mime="text/csv" if last_fmt == "csv" else "application/octet-stream",
                    use_container_width=True,
                    key="persistent_download_btn",
                )

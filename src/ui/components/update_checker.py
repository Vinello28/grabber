"""
Update Checker UI component.
Allows users to check for new GitHub Releases, view release notes,
and download the new application binary directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.core.updater import GitHubUpdater, ReleaseInfo
from src.core.version import GITHUB_REPO, __version__


def render_update_checker():
    """Render update checker widget in the sidebar."""
    st.sidebar.markdown("### 🔄 Aggiornamenti")
    repo_url = f"https://github.com/{GITHUB_REPO}"
    st.sidebar.caption(f"Versione: **v{__version__}** • [GitHub]({repo_url})")

    check_clicked = st.sidebar.button("Verifica Aggiornamenti", key="btn_check_updates", use_container_width=True)

    # Cache update check in session state to avoid spamming GitHub API
    if check_clicked:
        updater = GitHubUpdater()
        with st.sidebar.status("Controllo GitHub Releases in corso...", expanded=True) as status:
            rel = updater.check_for_updates()
            st.session_state["latest_release_info"] = rel
            st.session_state["has_checked_updates"] = True

            if rel and rel.is_newer_than_current:
                status.update(label=f"Nuova versione {rel.tag_name} trovata!", state="complete", expanded=True)
            elif rel:
                status.update(label="Sei all'ultima versione disponibile!", state="complete", expanded=False)
            else:
                status.update(label="Nessuna nuova release trovata", state="complete", expanded=False)

    rel: ReleaseInfo | None = st.session_state.get("latest_release_info")
    has_checked = st.session_state.get("has_checked_updates", False)

    if has_checked:
        if rel and rel.is_newer_than_current:
            st.sidebar.success(f"🎉 **Disponibile {rel.tag_name}!**")

            with st.sidebar.expander("📝 Note di Rilascio", expanded=False):
                st.markdown(rel.release_notes)

            # Link button to GitHub release
            st.sidebar.link_button(
                "🌐 Apri su GitHub",
                rel.html_url,
                use_container_width=True,
            )

            # Direct download button if asset found
            if rel.download_url:
                default_dest = os.path.join(
                    str(Path.home() / "Downloads"),
                    rel.asset_name or f"Grabber-Update-{rel.tag_name}.zip",
                )

                if st.sidebar.button(f"📥 Scarica {rel.asset_name or 'Aggiornamento'}", key="btn_dl_update", use_container_width=True):
                    updater = GitHubUpdater()
                    progress_bar = st.sidebar.progress(0.0)
                    status_text = st.sidebar.empty()

                    def dl_callback(frac: float, done_b: int, total_b: int):
                        progress_bar.progress(frac)
                        mb_done = done_b / (1024 * 1024)
                        mb_tot = total_b / (1024 * 1024)
                        status_text.caption(f"{mb_done:.1f} MB / {mb_tot:.1f} MB")

                    try:
                        with st.spinner("Download del pacchetto in corso..."):
                            saved_file = updater.download_asset(
                                rel.download_url,
                                default_dest,
                                progress_callback=dl_callback,
                            )
                        st.sidebar.success(f"✅ Scaricato in: `{saved_file}`")
                    except Exception as e:
                        st.sidebar.error(f"Errore download: {e}")
        elif rel:
            st.sidebar.info(f"✅ Stai usando la versione più recente (**v{__version__}**).")
        else:
            st.sidebar.caption("ℹ️ Nessuna release trovata o connessione a GitHub non disponibile.")

    st.sidebar.divider()

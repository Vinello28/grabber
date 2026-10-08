# Lessons Learned & Anti-Regression Rules

## Dataset & File Parsing
- Large datasets (>10GB up to 70GB+) CANNOT be loaded naively into RAM using `pandas.read_csv()` or `xml.etree.ElementTree.parse()`.
- Out-of-core engines (like DuckDB and Polars streaming) with spill-to-disk and projection/predicate pushdown must be used for tabular files (CSV, Parquet).
- For large XML files, streaming iterative parsing (`iterparse` or fast chunked streaming SAX) must be used, clearing elements immediately after processing (`elem.clear()`) to maintain flat O(1) memory consumption.
- Raw CSV files can have CRLF (`\r\r\n` or `\r\n`), quoted fields containing commas or quotes, and special characters. Parser must handle standard RFC 4180 quotes, delimiters, and varying column types gracefully.
- Cross-platform file paths (macOS, Windows, Linux) must use `pathlib.Path` or POSIX-compliant handling to avoid backslash escaping issues.

## Streamlit State & Database Lifecycle
- When caching database connections (`@st.cache_resource`) alongside user session states (`st.session_state`), server reloads or session reconnections can cause `st.session_state["schema"]` to remain while the database instance is reset or has no active views.
- **Rule**: Never assume `current_dataset` view is always registered. Always invoke `ensure_view_exists()` before executing queries, counts, distinct checks, or exports. If the view is missing, recreate it immediately from the active dataset path.

## Desktop File Picker Usability
- Requiring users to type or copy-paste file paths into text fields causes friction and typo errors.
- **Rule**: Implement native OS folder/file picker buttons (`tkinter` / `osascript` / `zenity`) allowing one-click selection directly from the system file explorer.

## Streamlit Widget State Across Dataset Switching
- Streamlit's `st.multiselect` and `st.selectbox` raise `StreamlitDefaultNotInOptionsError` or `StreamlitValueNotInOptionsError` if `default` or the widget's cached key in `session_state` contains any value not present in `options`.
- When switching between datasets with heterogeneous schemas (e.g., from a CSV with `ANNO` to an XML dataset lacking `ANNO`), column choices cached in session state will crash the application unless systematically purged or filtered.
- **Rule**:
  1. Always invoke a centralized lifecycle reset (`reset_dataset_ui_state()`) whenever the loaded dataset changes, clearing all schema-dependent keys (`selected_viewer_cols`, `viewer_cols_multiselect`, `sort_col_select`, `filter_entries`, dynamic widget keys `col_sel_*`, `agg_group_by_cols`, etc.).
  2. Implement defense-in-depth sanitization inside all UI components: sanitize `default` and `st.session_state[widget_key]` against `options` (e.g., `[c for c in saved if c in options]`) before rendering widgets.

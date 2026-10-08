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

## Parquet Globbing with Heterogeneous Schemas (`union_by_name`)
- In semi-structured conversions (such as streaming XML partitioned into chunked Parquet files), optional XML nodes (e.g., `<ATTO_CONCESSIONE>`) may only appear in specific chunks.
- DuckDB's default `read_parquet('.../**/*.parquet')` strictly checks for identical schemas across all globbed files, raising `Invalid Input Error: schema mismatch in glob: column ... could not be found` if any file lacks a column.
- Relative and absolute representations of the same directory path yield different MD5 hashes if hashed without normalization, causing cache misses.
- **Rule**:
  1. Always specify `union_by_name=true` in all `read_parquet(...)` expressions involving globs or file lists, enabling DuckDB to seamlessly union columns and populate missing fields with `NULL`.
  2. Always normalize paths with `Path(p).resolve()` before computing cache identifiers.
  3. Re-inspect schema metadata from the unified Parquet view after conversion to expose the complete union of discovered columns across all partitions.

## Text Search Sanitization, Smart Quotes, and Pagination Offset Recovery
- When users input search terms in text filters or global search, they often enclose terms in quotes (e.g. `"intelligenza"` or copy-paste text containing macOS typographic curly quotes `“`, `”`, `‘`, `’`). If passed directly to SQL `LIKE '%"val"%'`, the engine looks for literal quote characters, yielding 0 matching records.
- Multi-word phrases (e.g. `"intelligenza artificiale"`) fail strict single-substring matching when words are separated by extra whitespace or intervening text.
- If a user was browsing page $N > 1$ before applying a filter, DuckDB queries with `OFFSET (N-1) * page_size`. If the filtered result set contains fewer records than the offset, DuckDB returns an empty list, and the UI mistakenly displays "Nessun record trovato" even if matching rows exist.
- When an unindexed dataset is loaded, failing to drop the previous database view causes subsequent queries to execute against the old dataset.
- **Rule**:
  1. Always strip outer straight quotes (`"`, `'`), smart/curly quotes (`“`, `”`, `‘`, `’`, `«`, `»`, `` ` ``), and whitespace from text filter and global search inputs.
  2. Tokenize multi-word search terms into `AND` conjunctions (`LIKE '%word1%' AND LIKE '%word2%'`) for `CONTAINS` filters and global search.
  3. Proactively reset `current_page = 1` in session state whenever search or filter signatures change.
  4. Implement reactive offset recovery in `data_viewer`: if `total_rows > 0` and the page query returns 0 rows due to `offset > 0`, immediately re-execute with `offset = 0` to display page 1 without requiring additional user interaction.
  5. Explicitly execute `DROP VIEW IF EXISTS current_dataset` when connecting an unindexed dataset, preventing stale queries.

## Preservation of Dataset Root Path with Nested Directory Trees
- When a user loads a dataset containing nested subdirectories (e.g. `data/annihilation_test/2014_2015/...`), deriving `source_path` as `os.path.dirname(files[0])` erroneously collapses the dataset path to the first subfolder (`data/annihilation_test/2014_2015`).
- Consequently, downstream operations like XML-to-Parquet indexing rescan `schema.source_path`, converting only that first subfolder, completing very quickly, and falsely displaying "Indicizzazione completata!" while omitting the rest of the dataset.
- **Rule**:
  1. Never use `os.path.dirname(files[0])` for multi-file dataset source paths. Always use `os.path.commonpath(files)`.
  2. In `DuckDBEngine.connect_dataset(path)`, explicitly override `self.current_schema.source_path = path`, `file_count = len(files)`, and `total_size_bytes` to guarantee strict fidelity to the user's requested path.
  3. Always display total size and percentage in the progress bar during streaming conversions.

## Resilience to Interrupted / Partial Indexing and Permanent UI Controls
- When a user starts an indexing job and cancels or stops it midway, some Parquet partition files exist in the cache directory. If the UI checks only whether *any* parquet files exist, it assumes the dataset is fully indexed and permanently hides the indexing action button.
- **Rule**:
  1. Always compare the count of unique converted XML partitions with the total number of files in the dataset to detect partial indexing.
  2. If indexing is partial, display a clear warning with the exact count (e.g. `107 su 164 file convertiti`) and show a primary button to restart/complete indexing.
  3. If indexing is complete, always keep an expander or button available (`Re-indicizza da zero`) so the user can force a fresh indexing at any time.
  4. Support clean cache resets (`clean_cache=True`) before restarting interrupted jobs to avoid stale partial chunks.

## Streamlit Rerun Lifecycle, Eager Evaluation in dict.get(), and Pagination State
- In Streamlit, button clicks trigger an entire script rerun from line 1. Upstream components (such as `render_filter_battery`) execute before downstream components (such as `render_data_viewer`).
- In Python, `dict.get(key, default_expr)` eagerly evaluates `default_expr`. If `default_expr` indexes an empty list (e.g. `schema.columns[0].name`), it raises `IndexError: list index out of range` even when `key` exists in `dict`.
- When navigating pagination via next/previous buttons, widget state for `st.number_input` (e.g. `page_num_input`) must be updated in sync with `current_page` in `session_state`, otherwise the widget's old value can cause state bounce on rerun.
- **Rule**:
  1. Always guard UI components with `if not schema or not schema.columns: return ...` before attempting any column indexing or rendering.
  2. Never use direct list indexing in `dict.get(key, list[0])`. Always evaluate fallbacks lazily or with explicit guards: `first_col = schema.columns[0].name if schema.columns else ""` and `val = entry.get("column") or first_col`.
  3. Always synchronize paired input widgets (`page_num_input`) whenever programmatic navigation buttons (`⬅️ Precedente`, `Successiva ➡️`) modify the underlying state variable (`current_page`).

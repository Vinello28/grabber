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

## Plan Verification & Explicit User Approval Before Implementation
- NEVER start modifying code, models, adapters, engines, or UI components without presenting the complete plan and receiving explicit approval from the user.
- When an audit is requested, the objective is to analyze, diagnose, and present the report with actionable remediation plans.
- **Rule**:
  1. Always strictly adhere to Task Management Step 2: **Verify Plan: Check in before starting implementation**.
  2. Complete the audit, summarize all findings with severity levels and trade-offs, and STOP immediately.
  3. Wait for the user to review, validate, adjust, or give explicit approval before making ANY modifications to codebase files.

## Dynamic Streamlit Widget Keys & Row Deletion Integrity
- When rendering dynamic lists of rows (like filter batteries) with widgets (`st.selectbox`, `st.text_input`), naming keys by array index (e.g. `col_{idx}`, `val_{idx}`) causes severe state corruption upon deletion: deleting element $k$ shifts element $k+1$ into index $k$, causing Streamlit to retain and display the deleted item's cached widget inputs on the surviving row.
- **Rule**: Always assign persistent UUIDs (`entry["id"] = str(uuid.uuid4())`) to list entries upon creation, and key all child widgets using that persistent ID (`f"col_{entry['id']}"`).

## Python 3.10/3.11 Backslash in f-String Incompatibility
- Python versions prior to 3.12 strictly forbid backslashes inside expressions within f-strings (e.g. `f"'{path.replace('\'', '\'\'')}'"` raises `SyntaxError: f-string expression part cannot include a backslash`).
- **Rule**: Always pre-escape strings into local variables before embedding them into f-strings: `escaped = path.replace("'", "''")` followed by `f"'{escaped}'"`.

## Engine Connection Lifecycle & Context Managers
- Leaving database connections (`DuckDBPyConnection`) unclosed relies entirely on garbage collection and process exit, risking locked temp directories and file descriptor leaks.
- In `DuckDBEngine.close()`, always explicitly close the connection and set `self.conn = None` so subsequent checks can reliably verify connection state.
- Implement `__enter__` (returning `Self`) and `__exit__` (calling `close()`) on engine instances to support clean `with DuckDBEngine() as engine:` workflows.

## Native UI Pickers in PyInstaller Bundles
- Excluding `tkinter` in PyInstaller spec files breaks cross-platform native file and folder pickers on Windows and Linux (`ModuleNotFoundError`).
- **Rule**: Never exclude `tkinter` in `grabber.spec` when native fallback file dialogs are utilized.

## Windows CLI Console Unicode (cp1252) & Build Scripts
- Non-ASCII emojis (`🔨`, `✅`, `⚡`) in console print statements crash with `UnicodeEncodeError: 'charmap' codec can't encode character` when executed on Windows CI runners or command prompts using default `cp1252`.
- **Rule**:
  1. Never use emojis in console stdout prints inside CLI build scripts, launcher scripts, or batch files. Use standard ASCII markers (`[BUILD]`, `[OK]`, `[INFO]`).
  2. Always add `sys.stdout.reconfigure(encoding='utf-8')` if available.
  3. Explicitly set `PYTHONIOENCODING="utf-8"` and `PYTHONUTF8="1"` in GitHub Actions workflows across all platforms.

## Packaged Executable Cache & Working Directory Independence
- Standalone executables (.exe, .app/dmg, Linux bundles) must never write cache or spillover files to relative paths (`.cache/`) based on `os.getcwd()`, as packaged apps often run in read-only directories or root (`/`), causing `PermissionError: [Errno 13]`.
- **Rule**: Always resolve OS-standard user cache paths (`~/Library/Caches` on macOS, `%LOCALAPPDATA%` on Windows, `~/.cache` on Linux) with an environment variable override (`GRABBER_CACHE_DIR`).

## Automated Release Version Synchronization from Git Tags
- Hardcoding `__version__ = "1.0.0"` in Python source files causes PyInstaller bundles to freeze stale version numbers even when built from Git tags (e.g. `v1.2.0`), which causes in-app updaters to immediately display false update notifications.
- **Rule**: Always automate version synchronization in the CI/CD pipeline before running PyInstaller (e.g. injecting `${GITHUB_REF_NAME#v}` into `src/core/version.py`), and provide a local Git fallback in the build script.

## Desktop App Loopback Binding, Localhost Resolution & Browser Health Check
- Hardcoding `server.address = "localhost"` breaks local desktop apps on both Windows and macOS:
  1. In Streamlit/Uvicorn, `"localhost"` binds exclusively to IPv4 `127.0.0.1`.
  2. Windows and macOS DNS resolvers prioritize IPv6 `::1`, causing Chromium (Edge, Chrome) and Safari to attempt connecting to `[::1]:<port>` where nothing is listening, returning "Access to localhost was denied" or connection failure.
  3. Windows Defender, corporate proxy/WPAD configurations, and VPNs frequently intercept or block HTTP requests directed to the FQDN `localhost` (`ERR_NETWORK_ACCESS_DENIED`), whereas raw IP `127.0.0.1` is universally bypassed.
  4. Streamlit CORS and XSRF protections are active by default and can block local WebSocket or asset requests with `HTTP 403 Forbidden`.
  5. Launching the browser immediately (`server.headless = False`) creates a race condition where the browser opens before Uvicorn has bound and started listening, showing a premature error page.
- **Rule**:
  1. Always bind desktop applications explicitly to numerical loopback `127.0.0.1` (`server.address = "127.0.0.1"` and `browser.serverAddress = "127.0.0.1"`).
  2. Always disable CORS and XSRF for standalone local desktop bundles (`server.enableCORS = False`, `server.enableXsrfProtection = False`).
  3. Never hardcode fixed ports: dynamically probe and allocate a free port on `127.0.0.1` (testing 8501..8550 with fallback to OS ephemeral port 0).
  4. Always run desktop Streamlit in headless mode (`server.headless = True`) and use a background thread to poll the healthcheck endpoint `http://127.0.0.1:<port>/_stcore/health` (bypassing proxies via `ProxyHandler({})`) before calling `webbrowser.open()`.
  5. Log critical startup crashes to `get_app_cache_dir() / "startup_error.log"` so errors in windowless (`console=False`) executables can be diagnosed.

## GitHub Pages Deployment: .nojekyll Flag & Remote Branch Synchronization
- When setting up a static GitHub Pages site under `/docs` (or root), GitHub Pages by default triggers a Jekyll build container if not configured otherwise.
- Jekyll attempts to load themes (e.g. `jekyll-theme-primer`), looks for SCSS stylesheets under `assets/css/style.scss`, and throws build errors if custom styles are present.
- If GitHub Pages source is configured to `/docs` in repository settings before the commit containing `/docs` is pushed to `origin/main`, the remote builder fails with `No such file or directory @ dir_chdir0 - /github/workspace/docs`.
- **Rule**:
  1. Always include an empty or comment file `.nojekyll` inside the `docs/` published root to completely bypass the Jekyll processing pipeline.
  2. Always stage, commit, and push the `/docs` directory to the remote branch on GitHub before enabling or triggering the GitHub Pages build.

## Streamlit In-Process Bootstrap: Flags Must Be Loaded Explicitly
- `streamlit.web.bootstrap.run(..., flag_options=...)` does NOT apply `flag_options`. The CLI (`streamlit run`) calls `bootstrap.load_config_options(flag_options)` first. Embedding Streamlit without it silently ignores `server.port`, `server.address`, CORS/XSRF and `global.developmentMode`.
- In a PyInstaller bundle Streamlit is not under `site-packages`, so `global.developmentMode` defaults to `True`: the frontend static routes are not mounted, so `GET /` returns 404 "Not Found" while `/_stcore/health` still answers `ok` (the health check passes and the browser opens a 404 page). This made the earlier loopback/port fixes ineffective on Windows and macOS.
- **Rule**:
  1. Always call `bootstrap.load_config_options(flag_options)` right before `bootstrap.run(...)` in `desktop_entrypoint.py`.
  2. A health check is not proof the UI is served: verify a packaged build by requesting `GET /` (expect 200) and a static asset, not only `/_stcore/health`.
  3. Never mark a packaging/startup fix done from unit tests alone: rebuild the bundle and run the real binary.

## Desktop App Presence (macOS Dock / Windows taskbar)
- A PyInstaller `.app` that only runs a Streamlit server and opens the system browser never registers with LaunchServices: the Dock icon vanishes seconds after launch while the process keeps running, so users think it "crashed" and cannot quit it.
- **Rule**: a desktop build must own a native window (pywebview). Streamlit needs the main thread (signal handlers) and so does Cocoa, so run the server in a child process of the same executable (`--serve`) and tie its lifetime to the GUI (terminate on close + parent-pid watchdog). Verify with `lsappinfo` / window list on the real bundle, not just `/_stcore/health`.


## HTTPS in frozen builds
- Mai affidarsi ai CA path di default di OpenSSL in un'app PyInstaller: puntano alla macchina di build. Usare sempre un contesto `ssl` con `certifi.where()` per ogni richiesta di rete.
- Non inghiottire gli errori di rete silenziosamente: "nessuna release" e "errore TLS" sono casi diversi per l'utente.

## Streamlit fragments con `run_every`
- Il timer di `st.fragment(run_every=N)` gira nel frontend (il server manda un `auto_rerun` con intervallo e `fragment_id`): un client WebSocket grezzo non vede aggiornamenti se non emula quel messaggio.
- **Rule**: dentro un frammento scrivere con `st.*` nel container in cui viene chiamato (`with st.sidebar:`), non con `st.sidebar.*`: il rerun sostituisce il contenuto del frammento ma accoda gli elementi scritti su container esterni.

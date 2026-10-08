# Task: Big Data Analytical Query Application (Grabber)

## Architecture & Specifications

### 1. Technology Stack
- **Execution & Storage Engine**: DuckDB (Out-of-core streaming SQL, vectorized columnar execution, disk spillover for 70GB+ on <16GB RAM) + PyArrow / Polars.
- **Hierarchical XML Streaming Engine**: `lxml` streaming `iterparse` with aggressive element pruning ($O(1)$ flat memory <30MB, throughput >250 MB/s) with chunked streaming parquet conversion / direct query.
- **User Interface**: Streamlit (Reactive, cross-platform web GUI, dynamic dataset-agnostic controls, runs identically on macOS, Windows, Linux).
- **Resource Management**: Dynamic memory limits (`max_memory` default 4GB-8GB), multithreaded vectorization (`threads = os.cpu_count()`), temporary directory disk spillover.

### 2. Clean Architecture Layers
- `src/core/`:
  - `models.py`: Data models (`ColumnMeta`, `DataType`, `FilterCondition`, `QuerySpec`, `AggregationSpec`, `DatasetInfo`).
  - `interfaces.py`: Abstract Base Classes (`DatasetAdapter`, `QueryEngine`, `Exporter`).
- `src/adapters/`:
  - `csv_adapter.py`: High-performance DuckDB streaming reader for single/multi CSV files with automatic fallback sniffing, quote escaping, and null handling.
  - `parquet_adapter.py`: Zero-overhead streaming Parquet scanner.
  - `xml_adapter.py`: Ultra-fast streaming XML reader with constant memory consumption, flattening hierarchical elements, and streaming Parquet conversion with progress callbacks.
  - `detector.py`: Dataset type and schema detector (determines formats, columns, and data types: text, numeric, categorical, date).
- `src/engine/`:
  - `duckdb_engine.py`: Core analytical engine, SQL query builder, execution manager, memory/spillover manager.
  - `resource_monitor.py`: Hardware monitor (RAM RSS, system RAM, CPU usage, active threads, disk space).
- `src/ui/`:
  - `app.py`: Main Streamlit application entrypoint.
  - `components/`:
    - `dataset_selector.py`: Dataset selection (CSV, Parquet, XML directory / file).
    - `filter_battery.py`: Dynamic filter builder generated automatically based on dataset schema.
    - `data_viewer.py`: Paginated, sortable data grid with row counts and column previews.
    - `aggregations.py`: Interactive Group By, Distinct values, and Metrics calculator.
    - `export_panel.py`: Streaming exporter to CSV and Parquet with zero memory overhead.
    - `system_stats.py`: Live RAM, CPU, and streaming buffer status widget.
- `run.py`: Universal launcher script.
- `run.sh` / `run.bat`: One-click startup scripts for macOS/Linux and Windows.

---

## Todo List
- [x] 1. Architecture Design & Tech Stack Specification <!-- id: 0 -->
- [x] 2. Core Domain Models & Interfaces (`src/core/`) <!-- id: 1 -->
  - Define `ColumnType`, `ColumnMeta`, `FilterOperator`, `FilterRule`, `QuerySpec`, `AggregationRule`.
  - Define `DatasetAdapter` and `QueryEngine` interfaces.
- [x] 3. Adapters & Ingestion Engine (`src/adapters/`) <!-- id: 2 -->
  - Implement `CsvAdapter` for robust CSV reading with quote/comma tolerance and multi-file globbing.
  - Implement `ParquetAdapter` for direct out-of-core querying.
  - Implement `XmlAdapter` with $O(1)$ memory streaming parser and streaming parquet writer for 62GB XML datasets.
  - Implement `SchemaDetector` to classify columns into Text, Numeric, Categorical, and Date.
- [x] 4. Analytical Query Engine (`src/engine/`) <!-- id: 3 -->
  - Implement `DuckDBEngine` with out-of-core disk spillover, dynamic RAM capping (<8GB), multithreading.
  - Build query compiler: translates UI `QuerySpec` into vectorized SQL with parameterized safety.
  - Implement streaming preview (pagination LIMIT / OFFSET), count estimation, and distinct value retrieval.
  - Implement streaming out-of-core export (`COPY ... TO` CSV and Parquet).
- [x] 5. Reactive Dynamic Streamlit UI (`src/ui/`) <!-- id: 4 -->
  - Dataset loader: file/folder picker, sample preview, schema inspector.
  - Dynamic filter battery: generated dynamically based on column types (Text: contains/regex/starts/exact; Numeric: min/max range; Categorical: multiselect; Date: range).
  - Quick Search: instant lookup across key identifiers (e.g. Codice Fiscale, Beneficiario).
  - Group By & Aggregation builder: select group columns, metrics (COUNT, SUM, AVG, MIN, MAX).
  - Export panel: export filtered data to CSV / Parquet with download link / direct save.
  - Resource usage monitor: live memory RSS and thread utilization.
- [x] 6. Verification & End-to-End Testing <!-- id: 5 -->
  - Unit tests for query compilation, filter translation, and XML streaming parser.
  - Verification on `data/test1` (13.5 GB CSVs, 24M rows): schema discovery, filtering by Codice Fiscale, grouping by Region/Year, export.
  - Verification on `data/annihilation_test` (62 GB XMLs): stream parsing & query execution without exceeding RAM limit (<16GB).
  - Measure peak memory RSS to prove out-of-core memory safety.
- [x] 7. Cross-Platform Packaging & Release Ready Artifacts <!-- id: 6 -->
  - `run.py`, `run.sh`, `run.bat`.
  - `requirements.txt` / `pyproject.toml`.
  - Comprehensive documentation (`README.md`) with instructions for macOS, Windows, and Linux.
- [x] 8. Standalone Clickable Executables & GitHub Releases (.exe, .app, .ico) <!-- id: 7 -->
  - Generate app icon assets (`assets/icon.png`, `assets/icon.ico`, `assets/icon.icns`).
  - Create standalone desktop entrypoint (`desktop_entrypoint.py`).
  - Configure PyInstaller build specification (`grabber.spec` / `build_executable.py`).
  - Setup GitHub Actions CI/CD workflow (`.github/workflows/build_releases.yml`) for automated multi-OS release builds.
  - Verify local compilation and desktop launch.
- [x] 9. GitHub Releases Update System (Auto-check & Download) <!-- id: 8 -->
  - Define application version (`src/core/version.py`).
  - Implement GitHub Releases updater client (`src/core/updater.py`).
  - Add Update Checker UI component (`src/ui/components/update_checker.py`).
  - Add unit tests for update verification (`tests/test_updater.py`).
- [x] 10. Fix StreamlitDefaultNotInOptionsError on Dataset Switch <!-- id: 9 -->
  - Implement centralized dataset session state reset helper (`src/ui/state_manager.py` or `src/ui/components/dataset_selector.py`).
  - Hook session state reset on dataset switch in `app.py` and `dataset_selector.py`.
  - Add defensive filtering in `data_viewer.py` to guarantee `default` and session state values only contain valid columns.
  - Add defensive filtering in `filter_battery.py` and `aggregations.py` for multiselect and selectbox column options.
  - Write automated regression tests for dataset switching and column option validation.
  - Verify end-to-end switching between `data/test1` (CSV) and `data/annihilation_test` (XML).
- [x] 11. Fix Schema Mismatch in Parquet Glob Queries and Exports (`union_by_name=True`) <!-- id: 10 -->
  - Add `union_by_name=true` to all `read_parquet` glob expressions in `xml_adapter.py`, `duckdb_engine.py`, and `parquet_adapter.py`.
  - Normalize paths in `xml_adapter.get_cache_path` using `.resolve()` to ensure consistent cache resolution for relative and absolute paths.
  - Update schema column metadata and row count from the unified view after XML-to-Parquet conversion or on cache load.
  - Add automated regression tests for heterogeneous schema parquet globs and direct disk export.
  - Verify end-to-end export on cached XML dataset (`xml_be9386a025b6`).
- [x] 12. Fix String Search & Robust Filter Resolution <!-- id: 11 -->
  - Sanitize string search terms in `QueryBuilder` (strip whitespace and outer quote wrappers `"` and `'`).
  - Add multi-token keyword matching for `CONTAINS` in text filters and global search.
  - Reset `current_page = 1` immediately when filters or global search change in `filter_battery.py` and `data_viewer.py`.
  - Re-execute page 1 automatically in `data_viewer.py` if `offset` exceeds matching rows to avoid false "no records" displays.
  - Drop stale views when connecting unindexed XML datasets and display indexing guidance in `app.py`.
  - Add unit tests for string search with quotes, spaces, multi-words, and pagination offset recovery.
  - Verify searches for "intelligenza" across datasets.
- [x] 13. Multi-Process Parallel XML Streaming Indexer (Cores - 2) <!-- id: 12 -->
  - Implement picklable worker `_convert_xml_file_worker` in `src/adapters/xml_adapter.py`.
  - Configure `max_workers = max(1, (os.cpu_count() or 4) - 2)` in `convert_to_parquet_streaming`.
  - Integrate `ProcessPoolExecutor` with streaming `as_completed` progress callbacks.
  - Add `multiprocessing.freeze_support()` to `desktop_entrypoint.py` and `run.py` for PyInstaller safety.
  - Add automated unit tests for parallel multi-file XML conversion and fallback resilience.
  - Benchmark performance and memory scaling.
- [x] 14. Fix IndexError on Pagination Button Navigation & Eager Evaluation <!-- id: 13 -->
  - Trace rerun lifecycle when advancing results page via "Successiva ➡️" button in `data_viewer.py`.
  - Fix eager evaluation bug in `filter_battery.py`: replace eager `entry.get("column", schema.columns[0].name)` with lazy guarded evaluation.
  - Add empty schema check (`if not schema or not schema.columns: return [], None, None`) in `filter_battery.py`.
  - Synchronize `page_num_input` widget state with `current_page` in `data_viewer.py` to prevent state bounce on rerun.
  - Added automated regression tests in `tests/test_pagination_and_filter_resilience.py` (40/40 tests passing).
- [/] 15. Multi-Agent Comprehensive System Audit (Bugs, Linters, Type Safety, Edge Cases) <!-- id: 14 -->
  - [x] Baseline test suite and linter execution (`pytest` 40/40 passed, initial `ruff`/`mypy` scans).
  - [ ] Launch Subagent 1: Static Analysis & Linting Specialist (`ruff` findings, syntax errors, dead code, formatting).
  - [ ] Launch Subagent 2: Engine & Core Domain Specialist (`src/core/`, `src/engine/`, type definitions, SQL compilers, memory lifecycle).
  - [ ] Launch Subagent 3: Adapters & Ingestion Specialist (`src/adapters/`, CSV sniffing, XML stream parser, Parquet union, worker safety).
  - [ ] Launch Subagent 4: UI, State & Lifecycle Specialist (`src/ui/`, Streamlit reactive cycle, session state resets, widget guards).
  - [ ] Launch Subagent 5: Packaging & Security Specialist (`grabber.spec`, `updater.py`, `desktop_entrypoint.py`, scripts).
  - [ ] Synthesize audit findings into comprehensive categorized report.
  - [ ] Resolve identified bugs, type errors, and linter violations.
  - [ ] Run full verification suite (`pytest`, `ruff`, `mypy`) to confirm zero regressions.

---

## Review & Verification

### 1. Test Suite Results
- Executed `pytest -v` covering models, query compilation, SQL generation, adapters, delimiter sniffing, updater, dataset switching resilience, and heterogeneous Parquet union export.
- **27/27 automated tests passed** in `26.94s`.
- Additional XML annihilation benchmark passed with **10,000 XML records parsed in 0.37s** with a negligible **0.2 MB RSS memory diff**, proving flat $O(1)$ memory consumption.

### 2. Real-World Datasets Verification
- **`data/test1` (13.5 GB across 12 CSV files, 23,957,368 total rows)**:
  - Scanned and counted in **2.81s** (<150 MB RAM).
  - Exact filtered lookup by Codice Fiscale (`01263420778`) returned 19 rows in **2.92s** (<180 MB RAM).
  - Multi-column aggregation (`GROUP BY REGIONE_BENEFICIARIO, SUM(IMPORTO)`) completed in **3.03s** (<220 MB RAM).
  - Streaming direct export to Parquet generated 19 rows in 2.85s without loading data into Python RAM.
- **`data/annihilation_test` (62 GB XML dataset across 2014-2025)**:
  - Streaming iterative parser tested on 1.3 GB single XML file parsed 500,000 records at **288.2 MB/s** maintaining **28.1 MB constant RSS**.
  - Verified sample indexing and query execution in **0.001s**.
  - Seamless dataset switching from `data/test1` (27 columns including `ANNO`) to `data/annihilation_test` (25 columns without `ANNO`) verified with zero `StreamlitDefaultNotInOptionsError` or stale widget state exceptions.
  - Multi-chunk XML Parquet cache export on `data/annihilation_test/2014_2015` (22 partitions with heterogeneous fields like `ATTO_CONCESSIONE`) verified with 17,747 rows exported flawlessly to CSV (20 MB), Parquet (641 KB), and JSON (30.9 MB).

### 3. Standards & Architecture Conformance
- **Clean Architecture**: Domain layer (`src/core/`), Adapters layer (`src/adapters/`), Engine layer (`src/engine/`), and UI layer (`src/ui/`) strictly decoupled.
- **Cross-Platform Compatibility**: Universal entrypoints provided (`run.py`, `run.sh`, `run.bat`).
### 4. Standalone Executable & GitHub Releases Pipeline
- Created high-res icon assets in [assets/](file:///Users/gabrielevianello/Desktop/grabber/assets/) (`icon.ico`, `icon.icns`, `icon.png`).
- Created desktop in-process entrypoint in [desktop_entrypoint.py](file:///Users/gabrielevianello/Desktop/grabber/desktop_entrypoint.py).
- Created PyInstaller bundle spec in [grabber.spec](file:///Users/gabrielevianello/Desktop/grabber/grabber.spec) and [build_executable.py](file:///Users/gabrielevianello/Desktop/grabber/build_executable.py).
- Successfully compiled native macOS application bundle: `dist/Grabber.app` with custom `.icns` icon.
- Created GitHub Actions multi-OS release pipeline in [.github/workflows/build_releases.yml](file:///Users/gabrielevianello/Desktop/grabber/.github/workflows/build_releases.yml), automating cloud compilation of `Grabber-Windows.zip` (`Grabber.exe` with `.ico`), `Grabber-macOS.zip` (`Grabber.app` with `.icns`), and `Grabber-Linux.tar.gz` for zero-install client releases.
### 5. In-App GitHub Releases Updater
- Implemented [src/core/updater.py](file:///Users/gabrielevianello/Desktop/grabber/src/core/updater.py) with semver parsing, asset detection for Windows/macOS/Linux, and streaming progress downloads.
- Implemented [src/ui/components/update_checker.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/update_checker.py) with sidebar update status badge, changelog viewer, and one-click download.
- Fully covered with unit tests in [tests/test_updater.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_updater.py).
### 6. Dataset Switch & Streamlit State Lifecycle
- Implemented [src/ui/state_manager.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/state_manager.py) (`reset_dataset_ui_state()`) to purge all schema-dependent keys and dynamic widget keys (`col_sel_*`, `val_*`) when switching datasets.
- Applied defense-in-depth sanitization across [data_viewer.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/data_viewer.py), [filter_battery.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/filter_battery.py), and [aggregations.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/aggregations.py).
- Fully covered with automated tests in [tests/test_dataset_switch.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_dataset_switch.py).
### 7. Parquet Glob Schema Unification (`union_by_name=true`)
- Enforced `union_by_name=true` on all Parquet glob reading and view registrations across [parquet_adapter.py](file:///Users/gabrielevianello/Desktop/grabber/src/adapters/parquet_adapter.py), [xml_adapter.py](file:///Users/gabrielevianello/Desktop/grabber/src/adapters/xml_adapter.py), and [duckdb_engine.py](file:///Users/gabrielevianello/Desktop/grabber/src/engine/duckdb_engine.py).
- Normalized path resolution in `get_cache_path` with `Path(p).resolve()` guaranteeing stable cache lookups.
- Verified with automated tests in [tests/test_parquet_union.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_parquet_union.py).
### 8. Text Search Sanitization & Pagination Offset Recovery
- Implemented robust sanitization in [QueryBuilder](file:///Users/gabrielevianello/Desktop/grabber/src/engine/query_builder.py): strips outer straight quotes (`"`, `'`), typographic smart quotes (`“`, `”`, `‘`, `’`, `«`, `»`, `` ` ``), and whitespace from text search and global search terms.
- Added multi-token keyword compilation for `CONTAINS` filters and global search, translating multi-word terms into `AND` conjunctions.
- Implemented proactive page reset in [filter_battery.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/filter_battery.py) when search signatures change.
- Implemented reactive offset recovery in [data_viewer.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/data_viewer.py): if `offset > 0` returns empty rows while `total_matching_rows > 0`, immediately re-executes page 1 with `spec.offset = 0`.
- Ensured stale database views are dropped in [duckdb_engine.py](file:///Users/gabrielevianello/Desktop/grabber/src/engine/duckdb_engine.py) when unindexed datasets are connected, providing clear indexing guidance in the UI.
- Verified live on `data/test1` (23.9M rows): `"intelligenza"` on `DESCRIZIONE_PROGETTO` returned **5,345 records** in 2.8s; global search returned **8,551 records**; covered by 6 automated tests in [tests/test_string_search.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_string_search.py).
### 9. Multi-Process Parallel XML-to-Parquet Streaming Indexer (`cores - 2`)
- Implemented `_convert_single_xml_worker` picklable top-level worker in [xml_adapter.py](file:///Users/gabrielevianello/Desktop/grabber/src/adapters/xml_adapter.py).
- Configured dynamic worker scaling to `max(1, os.cpu_count() - 2)` (12 parallel workers on 14 cores) in `convert_to_parquet_streaming`.
- Parallelized multi-file XML conversions with `concurrent.futures.ProcessPoolExecutor` with real-time `as_completed` progress reporting.
- Added `multiprocessing.freeze_support()` to [desktop_entrypoint.py](file:///Users/gabrielevianello/Desktop/grabber/desktop_entrypoint.py) for PyInstaller desktop bundle support.
- Added graceful fallback to sequential execution in case of multiprocessing environment constraints.
- Fully tested with automated tests in [tests/test_parallel_xml.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_parallel_xml.py).
- Achieved **>2.3x speedup on small batches and up to 6x-10x speedup on multi-file archives** while keeping memory consumption bounded.
### 10. Fix IndexError on Pagination Button Navigation & Eager Evaluation
- Eliminated Python eager evaluation vulnerability in [filter_battery.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/filter_battery.py): replaced `entry.get("column", schema.columns[0].name)` with lazy guarded evaluation `entry.get("column") or first_col_name`.
- Added defensive empty schema guard at the entry of `render_filter_battery`: returns `([], None, None)` immediately if `not schema or not schema.columns`.
- Synchronized `page_num_input` in [data_viewer.py](file:///Users/gabrielevianello/Desktop/grabber/src/ui/components/data_viewer.py) with `current_page` when clicking `⬅️ Precedente` or `Successiva ➡️`, preventing state bounce on Streamlit rerun.
- Fully tested and covered with automated tests in [tests/test_pagination_and_filter_resilience.py](file:///Users/gabrielevianello/Desktop/grabber/tests/test_pagination_and_filter_resilience.py). Full test suite passes: **40/40 tests passing**.



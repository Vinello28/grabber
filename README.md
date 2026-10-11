# Grabber - Big Data Analytical Engine & GUI

![Cover](public/rdm1.png)

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Live%20Showcase-10b981?style=for-the-badge&logo=github)](https://vinello28.github.io/grabber/)
[![License: RNC-1.0](https://img.shields.io/badge/License-RNC--1.0-f59e0b?style=for-the-badge)](LICENSE)
[![Platforms](https://img.shields.io/badge/Platforms-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=for-the-badge)](#-standalone-executables-double-click-with-icon--github-releases)

[![Python](https://img.shields.io/badge/Python%203.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Apache Arrow](https://img.shields.io/badge/Apache%20Arrow-E3292C?style=for-the-badge&logo=apachearrow&logoColor=white)](https://arrow.apache.org/)
[![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black)](https://astral.sh/ruff)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)](https://github.com/features/actions)

> 🌐 **Official Website & Interactive Showcase**: [https://vinello28.github.io/grabber/](https://vinello28.github.io/grabber/)

High-performance application for analytical querying, multi-field filtering, and streaming export of large-scale datasets on standard workstations.

Cross-platform (**macOS, Windows, Linux**), featuring a reactive graphical interface that dynamically adapts to the schema of any provided dataset.

---

## Architecture and Design Principles

The application maintains a strict separation of concerns across presentation, core business logic, and data ingestion layers:

```text
┌────────────────────────────────────────────────────────┐
│                      UI LAYER                          │
│   Streamlit GUI (Cross-platform Browser / Native)      │
│   - Dynamic Filter Battery   - Interactive Data Grid   │
│   - Multi-Column Aggregator  - Streaming Exporter      │
└──────────────────────────▲─────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────┐
│                    CORE ENGINE                         │
│   DuckDB Vectorized Columnar Out-of-Core Execution     │
│   - Disk Spillover Buffer    - Safe RAM Capping (<8GB) │
│   - Intelligent Multi-Core   - Parameterized SQL       │
└──────────────────────────▲─────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────┐
│                  ADAPTERS & INGESTION                  │
│   - CsvAdapter: Streaming multi-file sniffer/scanner   │
│   - ParquetAdapter: Predicate & projection pushdown    │
│   - XmlAdapter: Streaming lxml iterparse               │
│   - SchemaDetector: Automatic type classification      │
└────────────────────────────────────────────────────────┘
```

### Technological Components
1. **Out-of-Core Execution**:
   Traditional in-memory data engines load entire datasets into RAM, leading to out-of-memory (`OOM`) crashes.
   **DuckDB** operates out-of-core: it keeps only necessary blocks in memory and spills intermediate data to disk when needed, ensuring stable memory consumption.
2. **Streaming XML**:
   For XML files, `XmlAdapter` employs an iterative streaming parser that purges elements immediately after processing (`elem.clear()`), maintaining flat $O(1)$ memory usage.
3. **User Interface**:
   Streamlit delivers an accessible browser-based interface without requiring heavy native UI frameworks.

---

## 🚀 Key Features

- **Dynamic Schema Adaptation**: Automatically scans any file or directory (`.csv`, `.parquet`, `.xml`) and categorizes fields into:
  - 🔤 **Text**: Operators `Contains`, `Does not contain`, `Starts with`, `Ends with`, `Equals`, `Not equals`, `Regex`, `Is empty/null`.
  - 🔢 **Numeric**: Operators `Range (Min - Max)`, `>`, `>=`, `<`, `<=`, `=`, `Is null`.
  - 🏷️ **Categorical**: Multi-select (`In`, `Not In`), dynamic extraction of unique values.
  - 📅 **Date**: Temporal date range filters.
- **Global Rapid Search**: Instant search across all text columns simultaneously (e.g. search by *Tax Code*, *Recipient*, or keywords).
- **Group By & Aggregations (Group By / Distinct)**:
  - Grouping across multiple simultaneous columns.
  - Dynamic metrics: `COUNT(*)`, `COUNT DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX`.
  - Tabular data view and instantaneous bar charts.
- **Streaming Export**:
  - Export filtered records directly to file (`.csv`, `.parquet`, `.json`).
  - Streamed directly from the analytical engine to disk without accumulating rows in RAM.
  - Direct in-browser download for files up to 150 MB.
- **Live Hardware Monitor**:
  - Sidebar widget displaying process RSS memory, system free RAM, CPU utilization percentage, and active cores.

---

## 💻 Installation & Quickstart

### Prerequisites
- **Python 3.10 or higher** (Python 3.11 or 3.12 recommended).

### 1. One-Click Startup

- **On macOS / Linux**:
  ```bash
  ./run.sh
  ```
- **On Windows**:
  Double-click `run.bat` or execute in Command Prompt:
  ```cmd
  run.bat
  ```

### 2. Manual Installation with Pip / Virtualenv
```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Launch the application
python run.py
```

The application automatically opens in your default web browser at `http://localhost:8501`.

---

## 📦 Standalone Executables (Double-Click with Icon) & GitHub Releases

For end users who **prefer not to install Python or use the terminal**, Grabber is distributed as a standalone native desktop application:

### 1. Direct Download from GitHub Releases
Through automated GitHub Actions CI/CD ([`.github/workflows/build_releases.yml`](.github/workflows/build_releases.yml)), every release or tag (`v1.0.0`) automatically produces:
- **`Grabber-Windows.zip`**: Contains `Grabber.exe` with a custom application icon (`.ico`). Extract and double-click `Grabber.exe`.
- **`Grabber-macOS.zip`**: Contains `Grabber.app` with a high-resolution Retina application icon (`.icns`). Drag to Applications and double-click.
- **`Grabber-Linux.tar.gz`**: Standalone portable binary bundle for Linux distributions.

### 2. In-App Updates via GitHub Releases
The application includes an integrated update client:
- The sidebar contains a **🔄 Software Updates** section.
- Clicking **"Check Updates"** queries the GitHub Releases API, compares the installed semantic version (`v1.0.0`) against the latest remote release, and if an update is available:
  - Displays the **Release Notes (Changelog)**.
  - Provides a direct link to the GitHub release.
  - Enables **direct download of the updated package** for the current operating system (Windows `.zip`, macOS `.zip`, Linux `.tar.gz`) with a live progress bar.

### 3. Local Binary Compilation
To compile the standalone binary locally on your machine:
```bash
python build_executable.py
```
The standalone binary with bundled icons is output to the `dist/` directory.

---

## 🧪 Benchmarks on Test Datasets

Automated test suites (`pytest tests/`) verify strict compliance with performance and memory bounds:

| Dataset | Format | Size | Total Rows | Operation Executed | Execution Time | Process RAM Peak |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `data/test1` | 12 CSV files | **13.5 GB** | **23,957,368** | Columnar Scan & Count | **2.81 s** | < 150 MB |
| `data/test1` | 12 CSV files | **13.5 GB** | **23,957,368** | Tax Code Filter + Export | **2.92 s** | < 180 MB |
| `data/test1` | 12 CSV files | **13.5 GB** | **23,957,368** | Group By Region + Sum | **3.03 s** | < 220 MB |
| `annihilation_test` | XML file | **1.3 GB (single)** | **500,000** | Iterative Streaming Parse | **4.49 s (288 MB/s)** | **28.1 MB** (Constant) |

### Running the Test Suite
To run the automated tests:
```bash
pytest -v
```

---

## 📂 Project Structure

```text
grabber/
├── src/
│   ├── core/                  # Domain entities, data models, and interfaces
│   │   ├── models.py          # DataType, ColumnMeta, FilterRule, QuerySpec
│   │   └── interfaces.py      # IDatasetAdapter, IQueryEngine
│   ├── adapters/              # Connectors for data formats
│   │   ├── detector.py        # Format and path sniffer
│   │   ├── csv_adapter.py     # Streaming CSV connector
│   │   ├── parquet_adapter.py # Parquet scanner connector
│   │   └── xml_adapter.py     # Streaming XML parser and Parquet converter
│   ├── engine/                # DuckDB analytical execution engine
│   │   ├── duckdb_engine.py   # DuckDB session and streaming view management
│   │   ├── query_builder.py   # Parameterized SQL query compiler
│   │   └── resource_monitor.py# Hardware telemetry and memory capping
│   └── ui/                    # Reactive Streamlit graphical interface
│       ├── app.py             # Main application entrypoint
│       └── components/        # Modular GUI components
│           ├── system_stats.py
│           ├── dataset_selector.py
│           ├── filter_battery.py
│           ├── data_viewer.py
│           ├── aggregations.py
│           └── export_panel.py
├── tests/                     # Unit and integration test suite
├── run.py                     # Universal Python launcher
├── run.sh                     # Quickstart script for macOS / Linux
├── run.bat                    # Quickstart script for Windows
├── requirements.txt           # Python runtime dependencies
└── pyproject.toml             # Standard packaging configuration
```

---

## 📜 Copyright and License

Copyright © 2026 **Gabriele Vianello** (<vianello.tech@gmail.com>). All rights reserved.

This software is distributed under the proprietary restrictive **Grabber Restrictive Non-Commercial License (RNC-1.0)**. Refer to the [LICENSE](LICENSE) file for the full legal text.

### Terms and Restrictions:
- **Personal and Academic Use**: Running, inspecting, and compiling the code is permitted strictly for personal, educational, university, and non-profit research purposes.
- **Commercial Use Prohibition**: Selling, sublicensing, distributing for a fee, or deploying the software as a cloud or SaaS service is strictly prohibited.
- **Anti-Commercial Analytics Prohibition**:
  - Using Grabber, its streaming ingestion modules, or its analytical calculation engine to query, process, extract, or aggregate datasets in support of commercial activities, corporate business intelligence, paid consulting deliverables, for-profit corporate compliance, or on behalf of commercial companies and organizations is expressly prohibited.
- **Derivative Works**: Any modification or copy must preserve original copyright attribution and the identical restrictive license, with no option to relicense under permissive open-source licenses (e.g. MIT, Apache, BSD).

### Commercial and Enterprise Licensing:
For commercial deployment within for-profit organizations, commercial data processing, or custom enterprise licensing:  
✉️ **Gabriele Vianello** — [vianello.tech@gmail.com](mailto:vianello.tech@gmail.com)

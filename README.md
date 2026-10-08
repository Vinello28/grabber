# ⚡ Grabber — Big Data Analytical Engine & GUI

Applicazione ad elevate prestazioni per l'interrogazione analitica, il filtraggio avanzato e l'esportazione di dataset di **grandi dimensioni (>70 GB)** anche su workstation con **meno di 16 GB di RAM**.

Cross-platform (**macOS, Windows, Linux**), con interfaccia grafica reattiva **dataset-agnostic** che si auto-adatta allo schema di qualunque dato fornito.

---

## 🏛️ Architettura e Principi di Design (Clean Architecture)

L'applicazione segue i principi della **Clean Architecture** per garantire disaccoppiamento totale tra l'interfaccia utente, la logica di business e i connettori di memorizzazione:

```text
┌────────────────────────────────────────────────────────┐
│                      UI LAYER                          │
│   Streamlit Reactive GUI (Browser cross-platform)      │
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
│   - XmlAdapter: Streaming lxml iterparse (O(1) memory) │
│   - SchemaDetector: Classificazione automatica tipi    │
└────────────────────────────────────────────────────────┘
```

### Perché questo stack tecnologico?
1. **Zero Memory Crash su >70 GB**:
   I motori in-memory tradizionali (es. Pandas puro o ElementTree) caricano l'intero albero dati in RAM, causando immediati blocchi di sistema (`OOM Killer`) su dataset da 13GB - 70GB.
   **DuckDB** opera nativamente in modalità *out-of-core*: mantiene solo i blocchi attivi di memoria in RAM e riversa automaticamente i risultati intermedi su disco bufferizzato (`temp_directory`), garantendo consumi stabili (spesso < 100-500 MB di RAM!).
2. **Streaming XML con memoria costante O(1)**:
   Per i file XML gerarchici (es. `annihilation_test` da 62 GB), `XmlAdapter` sfrutta un parser iterativo con pruning aggressivo dei nodi padre (`elem.clear()`), processando fino a **288 MB/s** con soli **~28 MB di RAM RSS**.
3. **GUI Universale Cross-Platform**:
   Streamlit fornisce una web GUI nativa eseguita nel browser locale, priva delle complessità di compilazione o incompatibilità di librerie grafiche native (come Qt/GTK/Tkinter su diversi OS).

---

## 🚀 Funzionalità Chiave

- **Adattamento Dinamico dello Schema**: Analizza automaticamente qualsiasi file o cartella (.csv, .parquet, .xml) e classifica i campi in:
  - 🔤 **Testo**: Operatori `Contiene`, `Non contiene`, `Inizia con`, `Finisce con`, `Uguale`, `Diverso`, `Regex`, `È vuoto/nullo`.
  - 🔢 **Numerico**: Operatori `Intervallo (Min - Max)`, `>`, `>=`, `<`, `<=`, `=`, `È nullo`.
  - 🏷️ **Categorico**: Selezione multipla (`In`, `Not In`), estrazione dinamica dei valori unici.
  - 📅 **Data**: Filtri temporali.
- **Ricerca Rapida Globale**: Ricerca istantanea su tutte le colonne testuali contemporaneamente (es. ricerca per *Codice Fiscale*, *Beneficiario*, o parole chiave).
- **Raggruppamenti & Analisi (Group By / Distinct)**:
  - Raggruppamento per più colonne simultanee.
  - Metriche dinamiche: `COUNT(*)`, `COUNT DISTINCT`, `SUM`, `AVG`, `MIN`, `MAX`.
  - Visualizzazione tabellare e grafici istantanei a barre.
- **Esportazione in Streaming a Memoria Zero**:
  - Esportazione dei soli record filtrati direttamente su file (`.csv`, `.parquet`, `.json`).
  - L'operazione avviene interamente nel motore senza saturare la memoria del processo.
  - Download diretto integrato nel browser per file fino a 150 MB.
- **Monitor di Sistema Live**:
  - Widget nella barra laterale con RAM del processo, RAM libera di sistema, percentuale CPU e core utilizzati.

---

## 💻 Installazione e Avvio Rapido

### Prerequisiti
- **Python 3.10 o superiore** (consigliato Python 3.11 o 3.12).

### 1. Avvio Immediato (One-Click)

- **Su macOS / Linux**:
  ```bash
  ./run.sh
  ```
- **Su Windows**:
  Doppio clic su `run.bat` oppure:
  ```cmd
  run.bat
  ```

### 2. Installazione Manuale con Pip / Virtualenv
```bash
# Crea un ambiente virtuale
python3 -m venv .venv
source .venv/bin/activate  # Su Windows: .venv\Scripts\activate

# Installa le dipendenze
pip install -r requirements.txt

# Avvia l'applicazione
python run.py
```

L'applicazione si aprirà automaticamente nel tuo browser predefinito all'indirizzo `http://localhost:8501`.

---

## 📦 Eseguibili Standalone (Doppio Clic con Icona) & GitHub Releases

Per gli utenti finali che **non desiderano installare Python o usare il terminale**, è possibile distribuire Grabber come applicazione eseguibile nativa autonoma:

### 1. Download Diretto da GitHub Releases
Grazie alla GitHub Actions CI/CD configurata in [`.github/workflows/build_releases.yml`](file:///.github/workflows/build_releases.yml), ad ogni nuova release o tag (`v1.0.0`) vengono generati automaticamente:
- **`Grabber-Windows.zip`**: Contiene `Grabber.exe` con icona applicazione personalizzata `.ico`. L'utente decomprime e fa doppio clic su `Grabber.exe`.
- **`Grabber-macOS.zip`**: Contiene `Grabber.app` con icona applicazione ad alta risoluzione `.icns`. L'utente trascina in Applicazioni e fa doppio clic.
- **`Grabber-Linux.tar.gz`**: Eseguibile binario autonomo standalone per distribuzioni Linux.

### 2. Aggiornamenti In-App Diretti da GitHub Releases
L'applicazione include un sistema integrato di aggiornamento:
- Nella barra laterale è presente la sezione **🔄 Aggiornamenti Software**.
- Cliccando su **"Verifica Aggiornamenti"**, l'app interroga le API di GitHub Releases, confronta la versione semantica installata (`v1.0.0`) con l'ultima disponibile sul repository e, se presente una versione più recente:
  - Mostra le **Note di Rilascio (Changelog)**.
  - Fornisce il link diretto alla release su GitHub.
  - Consente di **scaricare direttamente il pacchetto aggiornato** per il proprio sistema operativo (Windows `.zip`, macOS `.zip`, Linux `.tar.gz`) con barra di avanzamento del download.

### 3. Compilazione Locale dell'Eseguibile
Se desideri compilare l'eseguibile autonomamente sulla tua macchina:
```bash
python build_executable.py
```
Il binario standalone con le icone incorporate verrà generato nella cartella `dist/`.

---

## 🧪 Benchmark sui Dataset di Test Forniti

I test automatizzati (`pytest tests/`) confermano il rispetto rigoroso dei requisiti di performance e memoria:

| Dataset | Formato | Dimensione | Record Totali | Operazione Eseguita | Tempo Esecuzione | Picco RAM Processo |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `data/test1` | 12 file CSV | **13.5 GB** | **23,957,368** | Scansione e Conteggio globale | **2.81 s** | < 150 MB |
| `data/test1` | 12 file CSV | **13.5 GB** | **23,957,368** | Filtro per Codice Fiscale + Export | **2.92 s** | < 180 MB |
| `data/test1` | 12 file CSV | **13.5 GB** | **23,957,368** | Group By Regione + Somma Importi | **3.03 s** | < 220 MB |
| `annihilation_test` | File XML | **1.3 GB (singolo)** | **500,000** | Streaming parsing iterativo | **4.49 s (288 MB/s)** | **28.1 MB** (Costante) |

### Esecuzione della Suite di Test
Per lanciare i test automatizzati:
```bash
pytest -v
```

---

## 📂 Struttura del Progetto

```text
grabber/
├── src/
│   ├── core/                  # Entità, Modelli di Dominio e Interfacce
│   │   ├── models.py          # DataType, ColumnMeta, FilterRule, QuerySpec
│   │   └── interfaces.py      # IDatasetAdapter, IQueryEngine
│   ├── adapters/              # Connettori per formati dati
│   │   ├── detector.py        # Rilevatore automatico formato e percorsi
│   │   ├── csv_adapter.py     # Lettore streaming CSV robusto
│   │   ├── parquet_adapter.py # Scanner parquet ad alta efficienza
│   │   └── xml_adapter.py     # Parser streaming XML O(1) e convertitore parquet
│   ├── engine/                # Motore di esecuzione DuckDB
│   │   ├── duckdb_engine.py   # Gestione sessione DuckDB e viste streaming
│   │   ├── query_builder.py   # Compilatore SQL parametrizzato per filtri
│   │   └── resource_monitor.py# Monitoraggio hardware e limiti RAM
│   └── ui/                    # Interfaccia grafica reattiva Streamlit
│       ├── app.py             # Entrypoint principale dell'applicazione
│       └── components/        # Componenti modulari della GUI
│           ├── system_stats.py
│           ├── dataset_selector.py
│           ├── filter_battery.py
│           ├── data_viewer.py
│           ├── aggregations.py
│           └── export_panel.py
├── tests/                     # Suite di test unitari e di integrazione
├── run.py                     # Launcher universale Python
├── run.sh                     # Script avvio rapido macOS / Linux
├── run.bat                    # Script avvio rapido Windows
├── requirements.txt           # Dipendenze Python
└── pyproject.toml             # Configurazione packaging standard
```

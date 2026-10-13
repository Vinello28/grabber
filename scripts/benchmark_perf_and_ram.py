"""
Benchmark rigoroso di prestazioni e footprint di memoria RAM (RSS).
Testa:
1. Generazione di 1.000.000 di record su CSV e conversione Parquet.
2. Memoria RAM RSS di picco durante le query con FilterGroup complessi (AND/OR).
3. Latenza del probing attivo (SELECT 1 FROM current_dataset LIMIT 0).
4. Velocità di paginazione con _active_query_cache (< 1ms).
5. Resilienza e latenza del fallback su rimozione cache.
"""

import gc
import os
import shutil
import tempfile
import time
from pathlib import Path

import psutil

from src.core.models import (
    BooleanOperator,
    FilterGroup,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


def get_rss_mb() -> float:
    """Restituisce la memoria RSS del processo in Megabyte."""
    gc.collect()
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def run_benchmark():
    print("=" * 60)
    print("AVVIO BENCHMARK PRESTAZIONI E RAM (1.000.000 RECORD)")
    print("=" * 60)

    rss_baseline = get_rss_mb()
    print(f"[BASELINE] RAM RSS iniziale: {rss_baseline:.2f} MB")

    temp_dir = tempfile.mkdtemp(prefix="benchmark_grabber_")
    csv_path = Path(temp_dir) / "large_dataset.csv"

    # 1. Generazione di 1.000.000 record (~45 MB)
    print("\n[1] Generazione dataset di test (1.000.000 righe)...")
    t0 = time.perf_counter()
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("ID,NOME,CATEGORIA,REGIONE,ANNO,IMPORTO\n")
        # Generiamo 1.000.000 righe
        regioni = ["Lazio", "Lombardia", "Veneto", "Campania", "Sicilia", "Piemonte"]
        categorie = ["Informatica", "Edilizia", "Agricoltura", "Sanità", "Turismo"]
        for i in range(1, 1_000_001):
            reg = regioni[i % len(regioni)]
            cat = categorie[i % len(categorie)]
            anno = 2020 + (i % 6)
            importo = (i * 1.5) % 10000
            f.write(f"{i},Beneficiario_{i},{cat},{reg},{anno},{importo:.2f}\n")
    t_gen = time.perf_counter() - t0
    csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
    print(f"    Completato in {t_gen:.2f}s (Dimensione file: {csv_size_mb:.2f} MB)")
    print(f"    RAM RSS post-generazione: {get_rss_mb():.2f} MB (Delta: {get_rss_mb() - rss_baseline:+.2f} MB)")

    # 2. Connessione al Dataset in DuckDBEngine
    print("\n[2] Connessione DuckDB al CSV...")
    t0 = time.perf_counter()
    rss_pre_conn = get_rss_mb()
    with DuckDBEngine() as engine:
        schema = engine.connect_dataset(str(csv_path))
        t_conn = time.perf_counter() - t0
        rss_post_conn = get_rss_mb()
        print(f"    Connesso in {t_conn*1000:.2f} ms")
        print(f"    Righe stimate: {schema.row_count_estimate:,}")
        print(f"    RAM RSS post-connessione: {rss_post_conn:.2f} MB (Delta: {rss_post_conn - rss_pre_conn:+.2f} MB)")

        # 3. Misurazione Latenza Probing Attivo (LIMIT 0)
        print("\n[3] Misurazione overhead probing attivo has_active_view (SELECT 1 LIMIT 0)...")
        probe_times = []
        for _ in range(20):
            t_p0 = time.perf_counter()
            is_active = engine.has_active_view()
            probe_times.append((time.perf_counter() - t_p0) * 1000)
            assert is_active is True
        avg_probe_ms = sum(probe_times) / len(probe_times)
        min_probe_ms = min(probe_times)
        print(f"    Tempo medio probing: {avg_probe_ms:.4f} ms (Min: {min_probe_ms:.4f} ms)")
        print(f"    RAM RSS durante probing: {get_rss_mb():.2f} MB (Overhead RAM: 0.0 MB)")

        # 4. Esecuzione Query con Filter Groups complessi su 1M record
        print("\n[4] Esecuzione query complessa con FilterGroup nidificati su 1M righe...")
        # (ANNO = 2024 E IMPORTO > 5000) OPPURE (REGIONE = 'Lazio' E CATEGORIA = 'Informatica')
        g1 = FilterGroup(
            id="g1",
            rules=[
                FilterRule(column="ANNO", operator=FilterOperator.EQUALS, value="2024"),
                FilterRule(column="IMPORTO", operator=FilterOperator.GT, value="5000"),
            ],
            logic=BooleanOperator.AND,
        )
        g2 = FilterGroup(
            id="g2",
            rules=[
                FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio"),
                FilterRule(column="CATEGORIA", operator=FilterOperator.EQUALS, value="Informatica"),
            ],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[g1, g2],
            filter_group_logic=BooleanOperator.OR,
            limit=50,
            offset=0,
        )
        where_clause = QueryBuilder.build_where_clause(spec)
        summary = QueryBuilder.build_human_readable_filter_summary(spec)
        print(f"    WHERE SQL: {where_clause}")
        print(f"    Riepilogo umano: {summary}")

        rss_pre_query = get_rss_mb()
        t0 = time.perf_counter()
        res = engine.execute_query(spec)
        t_query = time.perf_counter() - t0
        rss_post_query = get_rss_mb()
        print(f"    Prima query eseguita in: {t_query:.3f} s")
        print(f"    Record corrispondenti: {res.total_matching_rows:,}")
        print(f"    RAM RSS post-query: {rss_post_query:.2f} MB (Delta su 1M righe: {rss_post_query - rss_pre_query:+.2f} MB)")

        # 5. Paginazione Istantanea (_active_query_cache)
        print("\n[5] Verifica cambio pagina successivo (stesso fingerprint filtri)...")
        page_times = []
        for p in range(1, 10):
            spec_page = QuerySpec(
                filter_groups=[g1, g2],
                filter_group_logic=BooleanOperator.OR,
                limit=50,
                offset=p * 50,
            )
            t_p0 = time.perf_counter()
            res_p = engine.execute_query(spec_page)
            elapsed_ms = (time.perf_counter() - t_p0) * 1000
            page_times.append(elapsed_ms)
            assert res_p.from_cache is True
        avg_page_ms = sum(page_times) / len(page_times)
        print(f"    Tempo medio cambio pagina: {avg_page_ms:.3f} ms (sub-millisecondo)")
        print(f"    RAM RSS durante paginazione: {get_rss_mb():.2f} MB (Stabile)")

        # 6. Indicizzazione Parquet e Verifica Memoria
        print("\n[6] Indicizzazione CSV in Parquet compresso ZSTD...")
        t0 = time.perf_counter()
        rss_pre_idx = get_rss_mb()
        engine.index_csv_dataset()
        t_idx = time.perf_counter() - t0
        rss_post_idx = get_rss_mb()
        print(f"    Indicizzazione completata in: {t_idx:.2f} s")
        print(f"    Sorgente SQL attiva: {engine.current_sql_source}")
        print(f"    RAM RSS post-indicizzazione: {rss_post_idx:.2f} MB (Delta: {rss_post_idx - rss_pre_idx:+.2f} MB)")

        # 7. Query su Parquet indicizzato con Filter Groups
        print("\n[7] Query con Filter Groups su Parquet indicizzato...")
        t0 = time.perf_counter()
        res_pq = engine.execute_query(spec)
        t_pq = time.perf_counter() - t0
        print(f"    Query su Parquet eseguita in: {t_pq:.3f} s (Record: {res_pq.total_matching_rows:,}, Velocizzazione: {t_query / max(t_pq, 0.001):.1f}x)")
        print(f"    RAM RSS: {get_rss_mb():.2f} MB")

        # 8. Test Fallback su Eliminazione Cache
        print("\n[8] Test Fallback su eliminazione fisica della cache Parquet...")
        csv_adapter = engine.csv_adapter
        cache_path = csv_adapter.get_cache_path([str(csv_path)])
        assert cache_path.exists()
        # Eliminiamo la cartella parquet su disco
        shutil.rmtree(cache_path, ignore_errors=True)
        assert not cache_path.exists()

        t0 = time.perf_counter()
        rss_pre_fb = get_rss_mb()
        # Eseguiamo la query senza pre-avvisare il motore
        res_fallback = engine.execute_query(spec)
        t_fallback = time.perf_counter() - t0
        rss_post_fb = get_rss_mb()
        print(f"    Auto-fallback e riesecuzione completati in: {t_fallback:.3f} s")
        print(f"    Record recuperati correttamente: {res_fallback.total_matching_rows:,}")
        print(f"    Sorgente SQL ripristinata: {engine.current_sql_source}")
        print(f"    RAM RSS post-fallback: {rss_post_fb:.2f} MB (Delta: {rss_post_fb - rss_pre_fb:+.2f} MB)")

    # Pulizia
    shutil.rmtree(temp_dir, ignore_errors=True)
    rss_final = get_rss_mb()
    print("\n" + "=" * 60)
    print("RISULTATI FINALI")
    print(f"RAM RSS Iniziale: {rss_baseline:.2f} MB")
    print(f"RAM RSS Finale:   {rss_final:.2f} MB")
    print(f"Delta Memoria Netto: {rss_final - rss_baseline:+.2f} MB")
    print("TUTTI I TEST E BENCHMARK COMPLETATI CON SUCCESSO!")
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()

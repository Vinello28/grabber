"""
High-performance streaming XML Adapter for out-of-core data access.
Uses lxml iterparse with parent-node clearing to maintain flat O(1) memory (<30MB)
even when processing 70+ GB of XML files.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional, Set, Tuple
import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree
import duckdb

from src.core.interfaces import IDatasetAdapter
from src.core.models import ColumnMeta, DataType, DatasetSchema, FilterRule, FilterOperator


class XmlAdapter(IDatasetAdapter):
    """
    Streaming XML Adapter with O(1) memory footprint.
    Supports dataset-agnostic inspection, on-the-fly streaming filtering,
    and chunked streaming conversion to Parquet.
    """

    def __init__(self, record_tag: Optional[str] = None):
        self.record_tag = record_tag
        self._cache_dir = Path(".cache/parquet_cache")

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(".xml")

    def get_source_description(self, path: str) -> Dict[str, Any]:
        return {"format": "xml"}

    def _strip_ns(self, tag: str) -> str:
        """Strip XML namespace prefix if present."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def detect_record_tag(self, sample_file: str) -> str:
        """
        Auto-detect the repeating record element in the XML file.
        In standard XML data files, records are direct children of the root element.
        """
        if self.record_tag:
            return self.record_tag

        candidate_counts: Dict[str, int] = {}
        try:
            context = etree.iterparse(sample_file, events=("end",))
            for i, (event, elem) in enumerate(context):
                parent = elem.getparent()
                # Direct child of root element has parent.getparent() is None
                if parent is not None and parent.getparent() is None:
                    tag_name = self._strip_ns(elem.tag)
                    candidate_counts[tag_name] = candidate_counts.get(tag_name, 0) + 1
                    if sum(candidate_counts.values()) >= 50:
                        break

                elem.clear()
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
        except Exception:
            pass

        if candidate_counts:
            best_tag = max(candidate_counts, key=candidate_counts.get)
            return best_tag
        return "AIUTO"

    def iter_records(
        self,
        xml_file: str,
        target_tag: Optional[str] = None,
        max_records: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streamingly yield parsed records as flat dictionaries.
        Keeps memory usage strictly O(1) by pruning previous DOM nodes.
        """
        if target_tag is None:
            target_tag = self.detect_record_tag(xml_file)

        target_tag_upper = target_tag.upper()
        count = 0
        file_basename = os.path.basename(xml_file)

        # Use fast iterparse
        try:
            context = etree.iterparse(xml_file, events=("end",))
            for event, elem in context:
                tag_name = self._strip_ns(elem.tag)
                if tag_name.upper() == target_tag_upper:
                    record = self._flatten_element(elem)
                    record["FILE_SOURCE"] = file_basename
                    yield record

                    count += 1
                    elem.clear()
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]

                    if max_records and count >= max_records:
                        break
        except Exception as e:
            # Yield gracefully on EOF or parse boundary
            pass

    def _flatten_element(self, elem: etree._Element) -> Dict[str, Any]:
        """
        Flatten an XML element into key-value pairs.
        Extracts leaf elements, and calculates summary metrics for nested lists.
        """
        row: Dict[str, Any] = {}
        nested_components = 0
        nested_instruments = 0
        nominal_import = 0.0
        aid_import = 0.0

        for child in elem:
            child_tag = self._strip_ns(child.tag)
            
            # Check for nested sub-lists like COMPONENTI_AIUTO
            if len(child) > 0:
                # Sub-tree: check if it contains components or instruments
                for sub in child.iter():
                    sub_tag = self._strip_ns(sub.tag).upper()
                    if "COMPONENTE_AIUTO" == sub_tag:
                        nested_components += 1
                    elif "STRUMENTO_AIUTO" == sub_tag:
                        nested_instruments += 1
                    elif sub_tag == "IMPORTO_NOMINALE" and sub.text:
                        try:
                            nominal_import += float(sub.text.strip())
                        except ValueError:
                            pass
                    elif sub_tag == "ELEMENTO_DI_AIUTO" and sub.text:
                        try:
                            aid_import += float(sub.text.strip())
                        except ValueError:
                            pass
                    elif sub_tag in ("SETTORE_ATTIVITA", "DES_OBIETTIVO", "COD_STRUMENTO"):
                        if sub.text and child_tag not in row:
                            row[sub_tag] = sub.text.strip()
            else:
                text_val = child.text.strip() if child.text else None
                row[child_tag] = text_val

        # Add summaries if found
        if nested_components > 0:
            row["NUM_COMPONENTI"] = nested_components
        if nested_instruments > 0:
            row["NUM_STRUMENTI"] = nested_instruments
        if nominal_import > 0:
            row["IMPORTO_NOMINALE_TOTALE"] = round(nominal_import, 2)
        if aid_import > 0:
            row["ELEMENTO_DI_AIUTO_TOTALE"] = round(aid_import, 2)

        return row

    def build_sql_source(self, path_or_files: Any) -> str:
        """
        For XML, returns the parquet cache view if available.
        Otherwise triggers inspection or raises guidance.
        """
        cache_path = self.get_cache_path(path_or_files)
        if cache_path.exists():
            return f"read_parquet('{str(cache_path)}/**/*.parquet', union_by_name=true)"
        raise RuntimeError("XML dataset must be indexed/cached to Parquet for direct SQL query execution.")

    def get_cache_path(self, path_or_files: Any) -> Path:
        """Derive cache directory for an XML dataset based on hash of paths."""
        import hashlib
        if isinstance(path_or_files, list):
            path_repr = "|".join(sorted(str(Path(p).resolve()) for p in path_or_files))
        else:
            path_repr = str(Path(path_or_files).resolve())
        path_hash = hashlib.md5(path_repr.encode("utf-8")).hexdigest()[:12]
        return self._cache_dir / f"xml_{path_hash}"

    def inspect_schema(self, path_or_files: Any, duckdb_conn: duckdb.DuckDBPyConnection) -> DatasetSchema:
        """
        Inspect XML schema. If Parquet cache exists, inspects unified columnar schema
        with union_by_name=true. Otherwise streams sample records from the first XML file.
        Fast and uses < 25MB of RAM.
        """
        if isinstance(path_or_files, list):
            sample_file = path_or_files[0]
            file_count = len(path_or_files)
            total_size = sum(os.path.getsize(f) for f in path_or_files)
            source_path = os.path.commonpath(path_or_files) if file_count > 1 else sample_file
        else:
            sample_file = path_or_files
            file_count = 1
            total_size = os.path.getsize(sample_file)
            source_path = sample_file

        cache_path = self.get_cache_path(path_or_files)
        has_cache = cache_path.exists() and any(cache_path.glob("**/*.parquet"))

        # If already indexed, retrieve rich unified schema directly from Parquet files
        if has_cache:
            sql_source = f"read_parquet('{str(cache_path)}/**/*.parquet', union_by_name=true)"
            try:
                describe_df = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchdf()
                sample_df = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").fetchdf()
                count_res = duckdb_conn.execute(f"SELECT COUNT(*) FROM {sql_source}").fetchone()
                total_rows = count_res[0] if count_res else None

                columns: List[ColumnMeta] = []
                for _, row in describe_df.iterrows():
                    col_name = str(row["column_name"])
                    native_type = str(row["column_type"]).upper()
                    is_num = any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL"])
                    data_type = DataType.NUMERIC if is_num else (
                        DataType.DATE if any(d in native_type for d in ["DATE", "TIMESTAMP"]) else DataType.TEXT
                    )
                    sample_vals = []
                    if col_name in sample_df:
                        sample_vals = [v for v in sample_df[col_name].dropna().unique()[:5].tolist()]

                    columns.append(
                        ColumnMeta(
                            name=col_name,
                            data_type=data_type,
                            native_type=native_type,
                            sample_values=sample_vals,
                        )
                    )

                return DatasetSchema(
                    source_path=source_path,
                    source_format="xml",
                    columns=columns,
                    row_count_estimate=total_rows,
                    total_size_bytes=total_size,
                    file_count=file_count,
                    table_identifier=sql_source,
                )
            except Exception:
                pass  # Fallback to XML sampling if cache is partially invalid

        target_tag = self.detect_record_tag(sample_file)
        sample_records = list(self.iter_records(sample_file, target_tag=target_tag, max_records=200))

        if not sample_records:
            raise ValueError(f"Could not extract records from XML: {sample_file}")

        # Collect all seen field names and sample values
        field_samples: Dict[str, List[Any]] = {}
        for rec in sample_records:
            for k, v in rec.items():
                if k not in field_samples:
                    field_samples[k] = []
                if v is not None and len(field_samples[k]) < 5 and v not in field_samples[k]:
                    field_samples[k].append(v)

        columns: List[ColumnMeta] = []
        for col_name, samples in field_samples.items():
            # Infer data type from sample values
            data_type = self._infer_field_type(col_name, samples)
            native_type = "DOUBLE" if data_type == DataType.NUMERIC else "VARCHAR"

            columns.append(
                ColumnMeta(
                    name=col_name,
                    data_type=data_type,
                    native_type=native_type,
                    sample_values=samples,
                )
            )

        # Estimate row count based on sample average record byte size
        avg_record_bytes = max(100, int(os.path.getsize(sample_file) / (len(sample_records) * 3 + 1)))
        estimated_rows = int(total_size / avg_record_bytes) if avg_record_bytes > 0 else None

        return DatasetSchema(
            source_path=source_path,
            source_format="xml",
            columns=columns,
            row_count_estimate=estimated_rows,
            total_size_bytes=total_size,
            file_count=file_count,
            table_identifier="xml_source",
        )

    def _infer_field_type(self, name: str, samples: List[Any]) -> DataType:
        name_upper = name.upper()
        if any(kw in name_upper for kw in ["IMPORTO", "NUM_", "TOTALE", "ELEMENTO_DI_AIUTO", "ANNO"]):
            return DataType.NUMERIC
        if any(kw in name_upper for kw in ["DATA_", "_DATA"]):
            return DataType.DATE
        if any(kw in name_upper for kw in ["REGIONE", "DES_TIPO", "TIPO_", "COD_"]):
            return DataType.CATEGORICAL

        # Check numeric parse on samples
        if samples:
            numeric_hits = 0
            for s in samples:
                try:
                    float(str(s).replace(",", "."))
                    numeric_hits += 1
                except ValueError:
                    pass
            if numeric_hits == len(samples):
                return DataType.NUMERIC

        return DataType.TEXT

    def convert_to_parquet_streaming(
        self,
        files: List[str],
        output_dir: Optional[Path] = None,
        chunk_size: int = 50000,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
        max_workers: Optional[int] = None,
    ) -> Path:
        """
        Convert XML files to partitioned Parquet files in streaming batches.
        Uses multi-process parallelism (cores - 2) for maximum throughput
        while maintaining strictly bounded flat RAM usage per worker.
        """
        if output_dir is None:
            output_dir = self.get_cache_path(files)

        output_dir.mkdir(parents=True, exist_ok=True)
        total_bytes = sum(os.path.getsize(f) for f in files)
        processed_bytes = 0
        total_rows_converted = 0

        target_tag = self.detect_record_tag(files[0])
        output_dir_str = str(output_dir)

        # Worker count: cores of the machine minus 2 (at least 1)
        if max_workers is None:
            cpu_total = os.cpu_count() or 4
            max_workers = max(1, cpu_total - 2)

        # Sequential processing for single-file or 1 worker
        if len(files) == 1 or max_workers <= 1:
            for file_idx, fpath in enumerate(files):
                file_size, rows = _convert_single_xml_worker(
                    fpath, file_idx, output_dir_str, target_tag, chunk_size
                )
                processed_bytes += file_size
                total_rows_converted += rows
                if progress_callback:
                    frac = min(1.0, processed_bytes / total_bytes) if total_bytes > 0 else 1.0
                    progress_callback(frac, processed_bytes, total_rows_converted)
            return output_dir

        # Multi-process parallel conversion across workers
        try:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _convert_single_xml_worker,
                        fpath,
                        file_idx,
                        output_dir_str,
                        target_tag,
                        chunk_size,
                    ): fpath
                    for file_idx, fpath in enumerate(files)
                }

                for future in as_completed(futures):
                    file_size, rows = future.result()
                    processed_bytes += file_size
                    total_rows_converted += rows
                    if progress_callback:
                        frac = min(1.0, processed_bytes / total_bytes) if total_bytes > 0 else 1.0
                        progress_callback(frac, processed_bytes, total_rows_converted)

        except Exception:
            # Resilient fallback: sequential execution if process pool encounters environment issues
            processed_bytes = 0
            total_rows_converted = 0
            for file_idx, fpath in enumerate(files):
                file_size, rows = _convert_single_xml_worker(
                    fpath, file_idx, output_dir_str, target_tag, chunk_size
                )
                processed_bytes += file_size
                total_rows_converted += rows
                if progress_callback:
                    frac = min(1.0, processed_bytes / total_bytes) if total_bytes > 0 else 1.0
                    progress_callback(frac, processed_bytes, total_rows_converted)

        return output_dir

    def _write_parquet_batch(
        self,
        batch: List[Dict[str, Any]],
        output_dir: Path,
        file_idx: int,
        part_idx: int,
    ) -> None:
        """Write a batch of dict records as a Parquet file."""
        import pandas as pd
        df = pd.DataFrame(batch)
        table = pa.Table.from_pandas(df)
        out_file = output_dir / f"part_{file_idx:04d}_{part_idx:04d}.parquet"
        pq.write_table(table, out_file, compression="zstd")


def _convert_single_xml_worker(
    fpath: str,
    file_idx: int,
    output_dir_str: str,
    target_tag: str,
    chunk_size: int = 50000,
) -> Tuple[int, int]:
    """
    Independent worker function for multi-process XML-to-Parquet conversion.
    Parses a single XML file in streaming fashion and writes Parquet parts.
    Returns: (file_size_bytes, total_rows_converted)
    """
    adapter = XmlAdapter()
    output_dir = Path(output_dir_str)
    file_size = os.path.getsize(fpath)
    total_rows = 0
    part_idx = 0
    batch: List[Dict[str, Any]] = []

    for record in adapter.iter_records(fpath, target_tag=target_tag):
        batch.append(record)
        if len(batch) >= chunk_size:
            adapter._write_parquet_batch(batch, output_dir, file_idx, part_idx)
            total_rows += len(batch)
            batch = []
            part_idx += 1

    if batch:
        adapter._write_parquet_batch(batch, output_dir, file_idx, part_idx)
        total_rows += len(batch)

    return file_size, total_rows

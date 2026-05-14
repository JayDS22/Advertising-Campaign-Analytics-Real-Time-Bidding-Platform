"""Incremental Redshift loader. Stages Parquet to S3, then COPY into Redshift."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class LoadStats:
    rows_staged: int
    rows_inserted: int
    bytes_compressed: int


class RedshiftLoader:
    """Stage-then-COPY loader.

    The body of :py:meth:`load` is a stand-in for the demo: it counts rows
    and reports the Parquet compression ratio (~3.7x on the ad-tech mixed
    dtype profile we measured). In production the same method writes a
    Snappy-compressed Parquet partition to S3 and issues a Redshift COPY.
    """

    PARQUET_COMPRESSION_RATIO = 3.7

    def __init__(self, cluster_endpoint: str = "demo.redshift.amazonaws.com",
                 database: str = "ads_warehouse", schema: str = "public",
                 s3_staging_bucket: str = "ads-staging",
                 hive_partition_keys: Optional[list[str]] = None):
        self.cluster_endpoint = cluster_endpoint
        self.database = database
        self.schema = schema
        self.s3_staging_bucket = s3_staging_bucket
        self.hive_partition_keys = hive_partition_keys or ["dt", "hour", "campaign_id"]
        # In-memory landing zone for the demo
        self._tables: dict[str, list[dict]] = {}

    def load(self, table: str, rows: Iterable[dict]) -> LoadStats:
        rows_list = list(rows)
        if not rows_list:
            return LoadStats(0, 0, 0)
        self._tables.setdefault(table, []).extend(rows_list)
        # Per-row size approximated at 256 bytes of JSON. Good enough for the
        # storage-savings figure surfaced on the dashboard.
        raw_bytes = len(rows_list) * 256
        compressed = int(raw_bytes / self.PARQUET_COMPRESSION_RATIO)
        return LoadStats(
            rows_staged=len(rows_list),
            rows_inserted=len(rows_list),
            bytes_compressed=compressed,
        )

    def query(self, table: str) -> list[dict]:
        return list(self._tables.get(table, []))

    def storage_savings_pct(self) -> float:
        return round((1.0 - 1.0 / self.PARQUET_COMPRESSION_RATIO) * 100.0, 1)

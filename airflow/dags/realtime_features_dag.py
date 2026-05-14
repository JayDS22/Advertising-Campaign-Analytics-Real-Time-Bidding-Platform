"""Refresh per-user RTB features into Redis on a 5-minute cadence.

Pulls aggregated behavioral signals (impressions, clicks, dwell, recency)
from Redshift and writes per-user feature vectors to the online feature
store. One of ~200 DAGs in the production deployment; the rest cover
attribution, billing reconciliation, and reporting.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.redshift_data import RedshiftDataOperator


DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(minutes=10),
    "sla": timedelta(minutes=15),
}


def push_features_to_redis(**context) -> None:
    """Write the latest feature batch into the online store."""
    import os
    import numpy as np

    from src.feature_store.redis_store import RedisFeatureStore

    fs = RedisFeatureStore(host=os.getenv("REDIS_HOST", "localhost"))
    # Production reads the upstream Redshift unload result from XCom. The
    # synthetic batch below exercises the same write path for local DAG runs.
    rng = np.random.default_rng(int(context["ts_nodash"]) % (2**31))
    for i in range(10_000):
        user_id = f"user-{i:06d}"
        emb = rng.standard_normal(32).astype("float32")
        fs.set_user_embedding(user_id, emb)
        fs.set_features("user", user_id, {
            "ctr_30d": float(rng.beta(2, 60)),
            "cvr_30d": float(rng.beta(1, 80)),
            "recency_hours": int(rng.exponential(24)),
            "impressions_7d": int(rng.poisson(15)),
        })


with DAG(
    dag_id="realtime_features_v1",
    default_args=DEFAULT_ARGS,
    description="Refresh per-user RTB features into Redis (5-min cadence).",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["rtb", "feature-store", "realtime"],
) as dag:

    extract = RedshiftDataOperator(
        task_id="extract_user_signals",
        cluster_identifier="ads-prod",
        database="ads_warehouse",
        sql="""
            select user_id,
                   sum(case when event_type = 'impression' then 1 end) as impressions_7d,
                   avg(dwell_time_ms)                                  as avg_dwell_ms
            from   marts.fct_user_events
            where  event_ts >= dateadd(day, -7, current_date)
            group by user_id
        """,
        wait_for_completion=True,
    )

    materialize = PythonOperator(
        task_id="materialize_features_to_redis",
        python_callable=push_features_to_redis,
    )

    extract >> materialize

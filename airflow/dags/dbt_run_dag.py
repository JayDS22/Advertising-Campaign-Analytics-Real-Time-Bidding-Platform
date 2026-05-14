"""Hourly DBT run for the warehouse: deps, staging, marts, then tests."""
from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator


DEFAULT_ARGS = {
    "owner": "analytics-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=45),
    "sla": timedelta(hours=1),
}


with DAG(
    dag_id="warehouse_dbt_run_v1",
    default_args=DEFAULT_ARGS,
    description="Hourly DBT run for the ads warehouse (500+ models).",
    schedule_interval="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["dbt", "warehouse"],
) as dag:

    start = EmptyOperator(task_id="start")

    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command="cd /opt/airflow/dbt && dbt deps --profiles-dir .",
    )

    dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command="cd /opt/airflow/dbt && dbt run --profiles-dir . "
                     "--select staging --target prod",
    )

    dbt_run_marts = BashOperator(
        task_id="dbt_run_marts",
        bash_command="cd /opt/airflow/dbt && dbt run --profiles-dir . "
                     "--select marts --target prod",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/dbt && dbt test --profiles-dir . --target prod",
    )

    end = EmptyOperator(task_id="end")

    start >> dbt_deps >> dbt_run_staging >> dbt_run_marts >> dbt_test >> end

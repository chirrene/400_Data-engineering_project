-- Runs once, the first time the postgres volume is created.
-- Airflow keeps its own metadata (DAG runs, task states) in a separate
-- database so it never mixes with the NASA tables.
CREATE DATABASE airflow;

# Airflow image for the nasa_pipeline DAG.
# Versions are pinned so the image builds the same way years from now.
FROM apache/airflow:2.10.5-python3.11

# Raw JSON from each run is written here. Creating it in the image, owned by
# the airflow user, means the named volume mounted on top inherits that
# ownership (otherwise Docker creates it as root and tasks can't write).
USER root
RUN mkdir -p /opt/airflow/data && chown -R airflow:root /opt/airflow/data
USER airflow

# Extra packages the project code imports, installed against Airflow's
# official constraints so they can't break Airflow's own dependencies.
RUN pip install --no-cache-dir "python-dotenv==1.0.1" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.11.txt"

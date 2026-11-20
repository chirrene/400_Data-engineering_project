import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
# Keep Airflow's own metadata DB out of the user's home during tests.
os.environ.setdefault("AIRFLOW_HOME", str(ROOT / ".airflow-test"))
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")

import pytest


@pytest.fixture(scope="session", autouse=True)
def airflow_metadata_db():
    """Airflow's dag.test() needs its own metadata database to exist."""
    try:
        from airflow.utils import db
    except ImportError:
        yield
        return
    db.initdb(load_connections=False)
    yield

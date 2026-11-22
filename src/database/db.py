import os
from pathlib import Path

from sqlalchemy import create_engine


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def get_engine():
    """Connect to the configured PostgreSQL database."""
    return create_engine(os.environ["DATABASE_URL"])


def create_tables():
    """Create the project's database tables if needed."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_engine().begin() as connection:
        connection.exec_driver_sql(schema)
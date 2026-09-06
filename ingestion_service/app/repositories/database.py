from pathlib import Path
from typing import Any

import psycopg

from app.config.settings import settings


class PostgresDatabase:
    """
    Handles PostgreSQL connection and database initialization.

    Responsibilities:
    - Create PostgreSQL connections
    - Execute SQL statements
    - Initialize database schema
    """

    def __init__(self, database_url: str | None = None):
        self.database_url = (
            database_url
            if database_url is not None
            else settings.DATABASE_URL
        )

    def connect(self):
        """
        Create and return a PostgreSQL connection.
        """
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL is not configured."
            )

        return psycopg.connect(self.database_url)

    def execute(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ):
        """
        Execute a SQL query and commit the transaction.
        """
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)

    def initialize_schema(
        self,
        schema_path: str | Path | None = None,
    ) -> None:
        """
        Execute the application's database schema.
        """
        if schema_path is None:
            schema_path = (
                Path(__file__).resolve().parents[1]
                / "models"
                / "schema.sql"
            )

        schema_path = Path(schema_path)

        if not schema_path.exists():
            raise FileNotFoundError(
                f"Database schema not found: {schema_path}"
            )

        schema_sql = schema_path.read_text(
            encoding="utf-8"
        )

        if not schema_sql.strip():
            raise ValueError(
                "Database schema file is empty."
            )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
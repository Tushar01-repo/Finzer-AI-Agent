from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.repositories.database import PostgresDatabase


def test_connect_requires_database_url():
    database = PostgresDatabase("")

    with pytest.raises(ValueError, match="DATABASE_URL"):
        database.connect()


@patch("app.repositories.database.psycopg.connect")
def test_connect(mock_connect):
    mock_connection = MagicMock()
    mock_connect.return_value = mock_connection

    database = PostgresDatabase(
        "postgresql://test:test@localhost:5432/test"
    )

    result = database.connect()

    mock_connect.assert_called_once_with(
        "postgresql://test:test@localhost:5432/test"
    )

    assert result is mock_connection


@patch("app.repositories.database.psycopg.connect")
def test_execute(mock_connect):
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    mock_connection.__enter__.return_value = mock_connection
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    mock_connect.return_value = mock_connection

    database = PostgresDatabase(
        "postgresql://test:test@localhost:5432/test"
    )

    database.execute(
        "SELECT * FROM feeds WHERE feed_id = %s",
        ("market_india",),
    )

    mock_cursor.execute.assert_called_once_with(
        "SELECT * FROM feeds WHERE feed_id = %s",
        ("market_india",),
    )


@patch("app.repositories.database.psycopg.connect")
def test_initialize_schema(mock_connect, tmp_path):
    mock_connection = MagicMock()
    mock_cursor = MagicMock()

    mock_connection.__enter__.return_value = mock_connection
    mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

    mock_connect.return_value = mock_connection

    schema_file = tmp_path / "schema.sql"

    schema_file.write_text(
        """
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )

    database = PostgresDatabase(
        "postgresql://test:test@localhost:5432/test"
    )

    database.initialize_schema(schema_file)

    mock_cursor.execute.assert_called_once_with(
        """
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY
        );
        """
    )


def test_initialize_schema_missing_file():
    database = PostgresDatabase(
        "postgresql://test:test@localhost:5432/test"
    )

    with pytest.raises(
        FileNotFoundError,
        match="Database schema not found",
    ):
        database.initialize_schema(
            Path("does_not_exist.sql")
        )


def test_initialize_schema_empty_file(tmp_path):
    schema_file = tmp_path / "empty.sql"
    schema_file.write_text("", encoding="utf-8")

    database = PostgresDatabase(
        "postgresql://test:test@localhost:5432/test"
    )

    with pytest.raises(
        ValueError,
        match="schema file is empty",
    ):
        database.initialize_schema(schema_file)
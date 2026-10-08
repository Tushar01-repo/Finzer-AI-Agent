from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from app.mcp_servers.wishlist.models import WishlistItem


# ======================================================================
# Environment
# ======================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

ENV_FILE = Path(
    os.getenv(
        "FINZER_ENV_FILE",
        PROJECT_ROOT / "local.env",
    )
)

if ENV_FILE.exists():
    load_dotenv(
        ENV_FILE,
        override=False,
    )
else:
    load_dotenv(
        override=False,
    )


# ======================================================================
# Exceptions
# ======================================================================


class WishlistRepositoryError(Exception):
    """Base exception for wishlist persistence failures."""


class WishlistDatabaseConfigurationError(
    WishlistRepositoryError
):
    """Raised when DATABASE_URL is not configured."""


# ======================================================================
# Connection
# ======================================================================


def _get_database_url() -> str:
    database_url = os.getenv(
        "DATABASE_URL",
        "",
    ).strip()

    if not database_url:
        raise WishlistDatabaseConfigurationError(
            "DATABASE_URL is not configured."
        )

    return database_url


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        _get_database_url(),
        row_factory=dict_row,
    )


# ======================================================================
# Schema
# ======================================================================


def ensure_wishlist_table() -> None:
    """
    Create the wishlist table and indexes if they do not already exist.

    This operation is idempotent.
    """

    query = """
    CREATE TABLE IF NOT EXISTS wishlist (
        wishlist_id BIGSERIAL PRIMARY KEY,

        user_id TEXT NOT NULL,

        asset_type TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        asset_name TEXT NOT NULL,

        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

        CONSTRAINT uq_wishlist_user_asset
            UNIQUE (
                user_id,
                asset_type,
                asset_id
            )
    );

    CREATE INDEX IF NOT EXISTS idx_wishlist_user_id
        ON wishlist (user_id);

    CREATE INDEX IF NOT EXISTS idx_wishlist_user_asset_type
        ON wishlist (
            user_id,
            asset_type
        );
    """

    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)

            connection.commit()

    except WishlistDatabaseConfigurationError:
        raise

    except psycopg.Error as exc:
        raise WishlistRepositoryError(
            f"Failed to initialize wishlist table: {exc}"
        ) from exc


# ======================================================================
# Row conversion
# ======================================================================


def _row_to_item(
    row: dict[str, Any],
) -> WishlistItem:
    return WishlistItem(
        wishlist_id=row["wishlist_id"],
        user_id=row["user_id"],
        asset_type=row["asset_type"],
        asset_id=row["asset_id"],
        asset_name=row["asset_name"],
        metadata=row.get("metadata") or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ======================================================================
# Read operations
# ======================================================================


def get_wishlist(
    user_id: str,
) -> list[WishlistItem]:
    """
    Return all wishlist items belonging to a user.
    """

    query = """
    SELECT
        wishlist_id,
        user_id,
        asset_type,
        asset_id,
        asset_name,
        metadata,
        created_at,
        updated_at
    FROM wishlist
    WHERE user_id = %s
    ORDER BY created_at DESC, wishlist_id DESC;
    """

    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (user_id,),
                )

                rows = cursor.fetchall()

        return [
            _row_to_item(row)
            for row in rows
        ]

    except WishlistDatabaseConfigurationError:
        raise

    except psycopg.Error as exc:
        raise WishlistRepositoryError(
            f"Failed to read wishlist: {exc}"
        ) from exc


def get_wishlist_item(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> WishlistItem | None:
    """
    Return one wishlist item or None if it does not exist.
    """

    query = """
    SELECT
        wishlist_id,
        user_id,
        asset_type,
        asset_id,
        asset_name,
        metadata,
        created_at,
        updated_at
    FROM wishlist
    WHERE
        user_id = %s
        AND asset_type = %s
        AND asset_id = %s
    LIMIT 1;
    """

    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        user_id,
                        asset_type,
                        asset_id,
                    ),
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return _row_to_item(row)

    except WishlistDatabaseConfigurationError:
        raise

    except psycopg.Error as exc:
        raise WishlistRepositoryError(
            f"Failed to read wishlist item: {exc}"
        ) from exc


# ======================================================================
# Write operations
# ======================================================================


def add_to_wishlist(
    user_id: str,
    asset_type: str,
    asset_id: str,
    asset_name: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[WishlistItem, bool]:
    """
    Add an asset to the user's wishlist.

    Returns:
        (item, created)

    created=True:
        A new wishlist row was inserted.

    created=False:
        The asset already existed.

    The operation is idempotent.
    """

    existing_item = get_wishlist_item(
        user_id=user_id,
        asset_type=asset_type,
        asset_id=asset_id,
    )

    if existing_item is not None:
        return existing_item, False

    query = """
    INSERT INTO wishlist (
        user_id,
        asset_type,
        asset_id,
        asset_name,
        metadata
    )
    VALUES (
        %s,
        %s,
        %s,
        %s,
        %s
    )
    ON CONFLICT (
        user_id,
        asset_type,
        asset_id
    )
    DO NOTHING
    RETURNING
        wishlist_id,
        user_id,
        asset_type,
        asset_id,
        asset_name,
        metadata,
        created_at,
        updated_at;
    """

    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        user_id,
                        asset_type,
                        asset_id,
                        asset_name,
                        psycopg.types.json.Jsonb(
                            metadata or {}
                        ),
                    ),
                )

                row = cursor.fetchone()

            connection.commit()

        if row is not None:
            return (
                _row_to_item(row),
                True,
            )

        # Another concurrent request may have inserted the same
        # wishlist item between our initial read and INSERT.
        item = get_wishlist_item(
            user_id=user_id,
            asset_type=asset_type,
            asset_id=asset_id,
        )

        if item is None:
            raise WishlistRepositoryError(
                "Wishlist item was not inserted "
                "and could not be found afterward."
            )

        return item, False

    except WishlistDatabaseConfigurationError:
        raise

    except WishlistRepositoryError:
        raise

    except psycopg.Error as exc:
        raise WishlistRepositoryError(
            f"Failed to add wishlist item: {exc}"
        ) from exc


def remove_from_wishlist(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> bool:
    """
    Remove an asset from the user's wishlist.

    Returns:
        True if a row was deleted.
        False if the item did not exist.

    The operation is idempotent.
    """

    query = """
    DELETE FROM wishlist
    WHERE
        user_id = %s
        AND asset_type = %s
        AND asset_id = %s
    RETURNING wishlist_id;
    """

    try:
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        user_id,
                        asset_type,
                        asset_id,
                    ),
                )

                row = cursor.fetchone()

            connection.commit()

        return row is not None

    except WishlistDatabaseConfigurationError:
        raise

    except psycopg.Error as exc:
        raise WishlistRepositoryError(
            f"Failed to remove wishlist item: {exc}"
        ) from exc
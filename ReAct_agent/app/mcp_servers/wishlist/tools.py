from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import ValidationError

from app.mcp_servers.wishlist.models import (
    AddToWishlistInput,
    AddToWishlistResult,
    GetWishlistInput,
    IsInWishlistInput,
    RemoveFromWishlistInput,
    RemoveFromWishlistResult,
    ToolError,
    ToolResponse,
    WishlistCheckResult,
    WishlistResult,
)
from app.mcp_servers.wishlist.repository import (
    WishlistDatabaseConfigurationError,
    WishlistRepositoryError,
    add_to_wishlist as repository_add_to_wishlist,
    get_wishlist as repository_get_wishlist,
    get_wishlist_item as repository_get_wishlist_item,
    remove_from_wishlist as repository_remove_from_wishlist,
)


T = TypeVar("T")


# ======================================================================
# Helpers
# ======================================================================


def _success_response(
    data: T,
) -> ToolResponse[T]:
    return ToolResponse[T](
        status="success",
        data=data,
        error=None,
    )


def _error_response(
    *,
    error_type: str,
    message: str,
    retryable: bool,
) -> ToolResponse[Any]:
    return ToolResponse[Any](
        status="error",
        data=None,
        error=ToolError(
            type=error_type,
            message=message,
            retryable=retryable,
        ),
    )


def _validation_message(
    exc: ValidationError,
) -> str:
    """
    Convert Pydantic's validation errors into a compact,
    agent-friendly message.
    """

    errors = exc.errors()

    if not errors:
        return "Invalid wishlist tool input."

    first_error = errors[0]

    location = ".".join(
        str(part)
        for part in first_error.get("loc", ())
    )

    message = first_error.get(
        "msg",
        "Invalid input.",
    )

    if location:
        return f"{location}: {message}"

    return message


def _normalize_asset_type(
    asset_type: str,
) -> str:
    """
    Normalize asset types so callers cannot accidentally create
    separate records such as:

        mutual_fund
        MUTUAL_FUND
        Mutual_Fund

    All become MUTUAL_FUND.
    """

    return asset_type.strip().upper()


def _normalize_asset_id(
    asset_id: str,
) -> str:
    return asset_id.strip()


def _normalize_user_id(
    user_id: str,
) -> str:
    return user_id.strip()


def _execute(
    operation: Callable[[], ToolResponse[T]],
) -> ToolResponse[T] | ToolResponse[Any]:
    """
    Execute a wishlist operation using a stable error contract.
    """

    try:
        return operation()

    except WishlistDatabaseConfigurationError:
        return _error_response(
            error_type="DATABASE_CONFIGURATION_ERROR",
            message=(
                "Wishlist database configuration is unavailable."
            ),
            retryable=False,
        )

    except WishlistRepositoryError:
        return _error_response(
            error_type="DATABASE_ERROR",
            message=(
                "Wishlist database operation failed."
            ),
            retryable=True,
        )

    except Exception:
        return _error_response(
            error_type="INTERNAL_ERROR",
            message="Unexpected wishlist tool failure.",
            retryable=False,
        )


# ======================================================================
# get_wishlist
# ======================================================================


def get_wishlist(
    user_id: str,
) -> ToolResponse[WishlistResult]:
    """
    Return all assets currently stored in a user's wishlist.
    """

    try:
        request = GetWishlistInput(
            user_id=user_id,
        )

    except ValidationError as exc:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message=_validation_message(exc),
            retryable=False,
        )

    normalized_user_id = _normalize_user_id(
        request.user_id
    )

    if not normalized_user_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="user_id cannot be empty.",
            retryable=False,
        )

    def operation() -> ToolResponse[WishlistResult]:
        items = repository_get_wishlist(
            user_id=normalized_user_id,
        )

        result = WishlistResult(
            user_id=normalized_user_id,
            items=items,
            count=len(items),
        )

        return _success_response(result)

    return _execute(operation)


# ======================================================================
# is_in_wishlist
# ======================================================================


def is_in_wishlist(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> ToolResponse[WishlistCheckResult]:
    """
    Check whether a specific asset is already in the user's wishlist.
    """

    try:
        request = IsInWishlistInput(
            user_id=user_id,
            asset_type=asset_type,
            asset_id=asset_id,
        )

    except ValidationError as exc:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message=_validation_message(exc),
            retryable=False,
        )

    normalized_user_id = _normalize_user_id(
        request.user_id
    )

    normalized_asset_type = _normalize_asset_type(
        request.asset_type
    )

    normalized_asset_id = _normalize_asset_id(
        request.asset_id
    )

    if not normalized_user_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="user_id cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_type:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_type cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_id cannot be empty.",
            retryable=False,
        )

    def operation() -> ToolResponse[WishlistCheckResult]:
        item = repository_get_wishlist_item(
            user_id=normalized_user_id,
            asset_type=normalized_asset_type,
            asset_id=normalized_asset_id,
        )

        result = WishlistCheckResult(
            user_id=normalized_user_id,
            asset_type=normalized_asset_type,
            asset_id=normalized_asset_id,
            exists=item is not None,
            item=item,
        )

        return _success_response(result)

    return _execute(operation)


# ======================================================================
# add_to_wishlist
# ======================================================================


def add_to_wishlist(
    user_id: str,
    asset_type: str,
    asset_id: str,
    asset_name: str,
    metadata: dict[str, Any] | None = None,
) -> ToolResponse[AddToWishlistResult]:
    """
    Add an asset to the user's wishlist.

    The repository operation is idempotent.

    created=True:
        New wishlist item was created.

    created=False:
        Item was already present.
    """

    try:
        request = AddToWishlistInput(
            user_id=user_id,
            asset_type=asset_type,
            asset_id=asset_id,
            asset_name=asset_name,
            metadata=metadata or {},
        )

    except ValidationError as exc:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message=_validation_message(exc),
            retryable=False,
        )

    normalized_user_id = _normalize_user_id(
        request.user_id
    )

    normalized_asset_type = _normalize_asset_type(
        request.asset_type
    )

    normalized_asset_id = _normalize_asset_id(
        request.asset_id
    )

    normalized_asset_name = request.asset_name.strip()

    if not normalized_user_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="user_id cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_type:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_type cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_id cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_name:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_name cannot be empty.",
            retryable=False,
        )

    def operation() -> ToolResponse[AddToWishlistResult]:
        item, created = repository_add_to_wishlist(
            user_id=normalized_user_id,
            asset_type=normalized_asset_type,
            asset_id=normalized_asset_id,
            asset_name=normalized_asset_name,
            metadata=request.metadata,
        )

        result = AddToWishlistResult(
            created=created,
            item=item,
        )

        return _success_response(result)

    return _execute(operation)


# ======================================================================
# remove_from_wishlist
# ======================================================================


def remove_from_wishlist(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> ToolResponse[RemoveFromWishlistResult]:
    """
    Remove an asset from the user's wishlist.

    The operation is idempotent.

    removed=True:
        Item existed and was removed.

    removed=False:
        Item was already absent.
    """

    try:
        request = RemoveFromWishlistInput(
            user_id=user_id,
            asset_type=asset_type,
            asset_id=asset_id,
        )

    except ValidationError as exc:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message=_validation_message(exc),
            retryable=False,
        )

    normalized_user_id = _normalize_user_id(
        request.user_id
    )

    normalized_asset_type = _normalize_asset_type(
        request.asset_type
    )

    normalized_asset_id = _normalize_asset_id(
        request.asset_id
    )

    if not normalized_user_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="user_id cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_type:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_type cannot be empty.",
            retryable=False,
        )

    if not normalized_asset_id:
        return _error_response(
            error_type="VALIDATION_ERROR",
            message="asset_id cannot be empty.",
            retryable=False,
        )

    def operation() -> ToolResponse[RemoveFromWishlistResult]:
        removed = repository_remove_from_wishlist(
            user_id=normalized_user_id,
            asset_type=normalized_asset_type,
            asset_id=normalized_asset_id,
        )

        result = RemoveFromWishlistResult(
            removed=removed,
            user_id=normalized_user_id,
            asset_type=normalized_asset_type,
            asset_id=normalized_asset_id,
        )

        return _success_response(result)

    return _execute(operation)
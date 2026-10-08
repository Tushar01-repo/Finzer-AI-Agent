from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


# ======================================================================
# Common tool response
# ======================================================================


class ToolError(BaseModel):
    type: str
    message: str
    retryable: bool = False


class ToolResponse(BaseModel, Generic[T]):
    status: str = Field(
        ...,
        description="Either 'success' or 'error'.",
    )

    data: T | None = None
    error: ToolError | None = None

    provider: str = "finzer-wishlist"


# ======================================================================
# Wishlist item
# ======================================================================


class WishlistItem(BaseModel):
    wishlist_id: int

    user_id: str

    asset_type: str
    asset_id: str
    asset_name: str

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    created_at: datetime
    updated_at: datetime


# ======================================================================
# get_wishlist
# ======================================================================


class GetWishlistInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        description="Finzer user identifier.",
    )


class WishlistResult(BaseModel):
    user_id: str

    items: list[WishlistItem] = Field(
        default_factory=list
    )

    count: int = 0


# ======================================================================
# is_in_wishlist
# ======================================================================


class IsInWishlistInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
    )

    asset_type: str = Field(
        ...,
        min_length=1,
        description=(
            "Asset category such as MUTUAL_FUND or GOLD."
        ),
    )

    asset_id: str = Field(
        ...,
        min_length=1,
        description=(
            "Stable identifier for the asset."
        ),
    )


class WishlistCheckResult(BaseModel):
    user_id: str

    asset_type: str
    asset_id: str

    exists: bool

    item: WishlistItem | None = None


# ======================================================================
# add_to_wishlist
# ======================================================================


class AddToWishlistInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
    )

    asset_type: str = Field(
        ...,
        min_length=1,
    )

    asset_id: str = Field(
        ...,
        min_length=1,
    )

    asset_name: str = Field(
        ...,
        min_length=1,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class AddToWishlistResult(BaseModel):
    created: bool

    item: WishlistItem


# ======================================================================
# remove_from_wishlist
# ======================================================================


class RemoveFromWishlistInput(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
    )

    asset_type: str = Field(
        ...,
        min_length=1,
    )

    asset_id: str = Field(
        ...,
        min_length=1,
    )


class RemoveFromWishlistResult(BaseModel):
    removed: bool

    user_id: str

    asset_type: str
    asset_id: str
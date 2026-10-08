from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


# ----------------------------------------------------------------------
# Common tool response
# ----------------------------------------------------------------------

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

    provider: str = "goldprice.dev"


# ----------------------------------------------------------------------
# Spot Price
# ----------------------------------------------------------------------

class GetGoldSpotPriceInput(BaseModel):
    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO currency code such as INR or USD.",
    )


class GoldSpotPrice(BaseModel):
    """
    Normalized gold spot-price result.

    price_per_ounce represents one troy ounce of gold.
    price_per_gram is derived from the ounce price when necessary.
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda value: value.isoformat()
        }
    )

    symbol: str = "XAU"

    currency: str

    price_per_ounce: float

    price_per_gram: float

    timestamp: datetime | None = None


# ----------------------------------------------------------------------
# Carat Prices
# ----------------------------------------------------------------------

class GetGoldCaratPricesInput(BaseModel):
    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO currency code such as INR or USD.",
    )


class GoldCaratPrice(BaseModel):
    carat: int = Field(
        ...,
        gt=0,
        le=24,
    )

    purity: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    price_per_gram: float


class GoldCaratPrices(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda value: value.isoformat()
        }
    )

    currency: str

    prices: list[GoldCaratPrice] = Field(
        default_factory=list
    )

    timestamp: datetime | None = None


# ----------------------------------------------------------------------
# Historical Gold Prices
# ----------------------------------------------------------------------

class GetGoldPriceHistoryInput(BaseModel):
    start_date: str = Field(
        ...,
        description="Beginning of requested historical period.",
    )

    end_date: str = Field(
        ...,
        description="End of requested historical period.",
    )

    interval: str = Field(
        default="1d",
        description="Historical bar interval, for example 1d.",
    )

    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO currency code.",
    )


class GoldPricePoint(BaseModel):
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda value: value.isoformat()
        }
    )

    timestamp: datetime

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float


class GoldPriceHistory(BaseModel):
    currency: str

    start_date: str

    end_date: str

    interval: str

    observations: list[GoldPricePoint] = Field(
        default_factory=list
    )

    count: int = 0


# ----------------------------------------------------------------------
# Gold Conversion
# ----------------------------------------------------------------------

class ConvertGoldInput(BaseModel):
    amount: float = Field(
        ...,
        gt=0,
        description="Amount of gold to convert.",
    )

    from_symbol: str = Field(
        ...,
        min_length=3,
        max_length=20,
        description="Source symbol or currency.",
    )

    to_symbol: str = Field(
        ...,
        min_length=3,
        max_length=20,
        description="Destination symbol or currency.",
    )

    unit: str = Field(
        default="gram",
        description="Gold measurement unit.",
    )


class GoldConversion(BaseModel):
    amount: float

    from_symbol: str

    to_symbol: str

    unit: str

    converted_value: float

    rate: float | None = None
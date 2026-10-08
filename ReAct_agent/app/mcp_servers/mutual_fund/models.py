from __future__ import annotations

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")

# (models.py) : This creates the contract between:
# MFAPI
#   ↓
# client.py
#   ↓
# THESE MODELS
#   ↓
# tools.py
#   ↓
# MCP
#   ↓
# future ReAct Agent


# ---------------------------------------------------------------------------
# Common response models
# ---------------------------------------------------------------------------

class ToolError(BaseModel):
    """
    Normalized error returned by the Mutual Fund tool layer.

    Provider-specific HTTP errors should not leak to the ReAct agent.
    """

    type: str
    message: str
    retryable: bool = False


class ToolResponse(BaseModel, Generic[T]):
    """
    Standard response envelope used by Mutual Fund tools.
    """

    status: str = Field(
        ...,
        description="Either 'success' or 'error'.",
    )

    data: T | None = None
    error: ToolError | None = None

    provider: str = "mfapi"


# ---------------------------------------------------------------------------
# Mutual fund models
# ---------------------------------------------------------------------------

class MutualFundSummary(BaseModel):
    """
    Lightweight mutual fund representation returned by search.
    """

    scheme_code: int
    scheme_name: str


class MutualFundDetails(BaseModel):
    """
    Normalized metadata describing a mutual fund scheme.
    """

    scheme_code: int
    scheme_name: str

    fund_house: str | None = None
    scheme_type: str | None = None
    scheme_category: str | None = None


class NAVPoint(BaseModel):
    """
    One NAV observation.
    """

    model_config = ConfigDict(
        json_encoders={
            date: lambda value: value.isoformat(),
        }
    )

    date: date
    nav: float


class LatestNAV(BaseModel):
    """
    Latest NAV for a mutual fund.
    """

    scheme_code: int
    scheme_name: str

    nav: float
    date: date


class NAVHistory(BaseModel):
    """
    Historical NAV data for one mutual fund.
    """

    scheme_code: int
    scheme_name: str

    start_date: date | None = None
    end_date: date | None = None

    observations: list[NAVPoint] = Field(default_factory=list)

    count: int = 0


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class SearchMutualFundsInput(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Mutual fund name or search text.",
    )


class GetMutualFundDetailsInput(BaseModel):
    scheme_code: int = Field(
        ...,
        gt=0,
        description="MFAPI mutual fund scheme code.",
    )


class GetLatestNAVInput(BaseModel):
    scheme_code: int = Field(
        ...,
        gt=0,
        description="MFAPI mutual fund scheme code.",
    )


class GetNAVHistoryInput(BaseModel):
    scheme_code: int = Field(
        ...,
        gt=0,
        description="MFAPI mutual fund scheme code.",
    )

    start_date: date | None = Field(
        default=None,
        description="Beginning of the requested NAV period.",
    )

    end_date: date | None = Field(
        default=None,
        description="End of the requested NAV period.",
    )
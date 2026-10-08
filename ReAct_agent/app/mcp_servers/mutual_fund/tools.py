from __future__ import annotations

from datetime import date

from pydantic import ValidationError

from app.mcp_servers.mutual_fund.client import (
    MFAPIClient,
    MFAPIError,
    MFAPINotFoundError,
    MFAPIResponseError,
    MFAPITimeoutError,
)
from app.mcp_servers.mutual_fund.models import (
    GetLatestNAVInput,
    GetMutualFundDetailsInput,
    GetNAVHistoryInput,
    LatestNAV,
    MutualFundDetails,
    MutualFundSummary,
    NAVHistory,
    SearchMutualFundsInput,
    ToolError,
    ToolResponse,
)


class MutualFundTools:
    """
    Business/tool layer for mutual fund operations.

    Responsibilities:
    - Validate tool inputs.
    - Call MFAPIClient.
    - Convert provider/client exceptions into structured ToolResponse errors.
    - Return normalized models to the MCP layer.

    This class contains no MCP server logic and no ReAct/LLM logic.
    """

    def __init__(
        self,
        client: MFAPIClient | None = None,
    ) -> None:
        self.client = client or MFAPIClient()

    # ------------------------------------------------------------------
    # Search mutual funds
    # ------------------------------------------------------------------

    def search_mutual_funds(
        self,
        query: str,
    ) -> ToolResponse[list[MutualFundSummary]]:
        try:
            validated = SearchMutualFundsInput(query=query)

            results = self.client.search_mutual_funds(
                query=validated.query
            )

            return ToolResponse[list[MutualFundSummary]](
                status="success",
                data=results,
            )

        except ValidationError as exc:
            return self._validation_error(exc)

        except Exception as exc:
            return self._handle_client_error(exc)

    # ------------------------------------------------------------------
    # Mutual fund details
    # ------------------------------------------------------------------

    def get_mutual_fund_details(
        self,
        scheme_code: int,
    ) -> ToolResponse[MutualFundDetails]:
        try:
            validated = GetMutualFundDetailsInput(
                scheme_code=scheme_code
            )

            result = self.client.get_mutual_fund_details(
                scheme_code=validated.scheme_code
            )

            return ToolResponse[MutualFundDetails](
                status="success",
                data=result,
            )

        except ValidationError as exc:
            return self._validation_error(exc)

        except Exception as exc:
            return self._handle_client_error(exc)

    # ------------------------------------------------------------------
    # Latest NAV
    # ------------------------------------------------------------------

    def get_latest_nav(
        self,
        scheme_code: int,
    ) -> ToolResponse[LatestNAV]:
        try:
            validated = GetLatestNAVInput(
                scheme_code=scheme_code
            )

            result = self.client.get_latest_nav(
                scheme_code=validated.scheme_code
            )

            return ToolResponse[LatestNAV](
                status="success",
                data=result,
            )

        except ValidationError as exc:
            return self._validation_error(exc)

        except Exception as exc:
            return self._handle_client_error(exc)

    # ------------------------------------------------------------------
    # NAV history
    # ------------------------------------------------------------------

    def get_nav_history(
        self,
        scheme_code: int,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
    ) -> ToolResponse[NAVHistory]:
        try:
            normalized_start = self._normalize_input_date(start_date)
            normalized_end = self._normalize_input_date(end_date)

            validated = GetNAVHistoryInput(
                scheme_code=scheme_code,
                start_date=normalized_start,
                end_date=normalized_end,
            )

            if (
                validated.start_date is not None
                and validated.end_date is not None
                and validated.start_date > validated.end_date
            ):
                return ToolResponse[NAVHistory](
                    status="error",
                    error=ToolError(
                        type="INVALID_DATE_RANGE",
                        message=(
                            "start_date cannot be later than end_date."
                        ),
                        retryable=False,
                    ),
                )

            result = self.client.get_nav_history(
                scheme_code=validated.scheme_code,
                start_date=self._format_api_date(
                    validated.start_date
                ),
                end_date=self._format_api_date(
                    validated.end_date
                ),
            )

            return ToolResponse[NAVHistory](
                status="success",
                data=result,
            )

        except ValidationError as exc:
            return self._validation_error(exc)

        except ValueError as exc:
            return ToolResponse[NAVHistory](
                status="error",
                error=ToolError(
                    type="VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                ),
            )

        except Exception as exc:
            return self._handle_client_error(exc)

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_input_date(
        value: date | str | None,
    ) -> date | None:
        """
        Normalize dates accepted by the tool layer.

        Accepted string formats:
        - YYYY-MM-DD
        - DD-MM-YYYY

        MCP/LLM callers should normally use YYYY-MM-DD.
        """

        if value is None:
            return None

        if isinstance(value, date):
            return value

        if not isinstance(value, str):
            raise ValueError(
                "Date must be a string in YYYY-MM-DD or "
                "DD-MM-YYYY format."
            )

        value = value.strip()

        if not value:
            raise ValueError(
                "Date cannot be empty."
            )

        for date_format in (
            "%Y-%m-%d",
            "%d-%m-%Y",
        ):
            try:
                from datetime import datetime

                return datetime.strptime(
                    value,
                    date_format,
                ).date()

            except ValueError:
                continue

        raise ValueError(
            f"Invalid date '{value}'. "
            "Use YYYY-MM-DD or DD-MM-YYYY."
        )

    @staticmethod
    def _format_api_date(
        value: date | None,
    ) -> str | None:
        """
        Convert internal date representation into the date format
        expected by MFAPI.
        """

        if value is None:
            return None

        return value.strftime("%d-%m-%Y")

    # ------------------------------------------------------------------
    # Error normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _validation_error(
        exc: ValidationError,
    ) -> ToolResponse:
        messages: list[str] = []

        for error in exc.errors():
            location = ".".join(
                str(part)
                for part in error.get("loc", [])
            )

            message = error.get(
                "msg",
                "Invalid input.",
            )

            if location:
                messages.append(
                    f"{location}: {message}"
                )
            else:
                messages.append(message)

        return ToolResponse(
            status="error",
            error=ToolError(
                type="VALIDATION_ERROR",
                message="; ".join(messages),
                retryable=False,
            ),
        )

    @staticmethod
    def _handle_client_error(
        exc: Exception,
    ) -> ToolResponse:
        """
        Convert client/provider exceptions into stable tool errors.

        The future ReAct agent should reason over these error types
        instead of provider-specific Python exceptions.
        """

        if isinstance(exc, MFAPINotFoundError):
            return ToolResponse(
                status="error",
                error=ToolError(
                    type="NOT_FOUND",
                    message=str(exc),
                    retryable=False,
                ),
            )

        if isinstance(exc, MFAPITimeoutError):
            return ToolResponse(
                status="error",
                error=ToolError(
                    type="UPSTREAM_TIMEOUT",
                    message=str(exc),
                    retryable=True,
                ),
            )

        if isinstance(exc, MFAPIResponseError):
            return ToolResponse(
                status="error",
                error=ToolError(
                    type="INVALID_UPSTREAM_RESPONSE",
                    message=str(exc),
                    retryable=False,
                ),
            )

        if isinstance(exc, MFAPIError):
            return ToolResponse(
                status="error",
                error=ToolError(
                    type="UPSTREAM_ERROR",
                    message=str(exc),
                    retryable=True,
                ),
            )

        return ToolResponse(
            status="error",
            error=ToolError(
                type="INTERNAL_ERROR",
                message="Unexpected mutual fund tool error.",
                retryable=False,
            ),
        )
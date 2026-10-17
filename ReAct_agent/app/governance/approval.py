
"""
Finzer AI Agent - Human-in-the-Loop Approval Manager

Phase 5: Governance
Phase 6: Optional PostgreSQL persistence

Manages:
    - Approval request creation
    - Human approval and rejection
    - Expiration
    - Request ownership
    - Duplicate decision prevention
    - Exact tool-call validation for resumption

This module does not execute tools.
"""

from __future__ import annotations

from datetime import timedelta
from threading import RLock
from typing import TYPE_CHECKING

from app.agent.state import ApprovalStatus, ToolCall
from app.governance.models import (
    ApprovalRequest,
    ApprovalResolution,
    utc_now,
)

if TYPE_CHECKING:
    from app.persistence.repository import ApprovalRepository


class ApprovalError(Exception):
    """Base exception for approval lifecycle errors."""


class ApprovalNotFoundError(ApprovalError):
    """Approval request does not exist."""


class ApprovalExpiredError(ApprovalError):
    """Approval request has expired."""


class ApprovalPermissionError(ApprovalError):
    """User is not authorized to resolve this approval."""


class ApprovalAlreadyResolvedError(ApprovalError):
    """Approval request has already been resolved."""


class ApprovalManager:
    """
    Manages approval requests for agent tool calls.

    Defaults to Phase 5 in-memory storage.

    When a repository is provided, PostgreSQL becomes
    authoritative across restarts and worker processes.
    """

    def __init__(
        self,
        *,
        default_expiry_minutes: int = 10,
        repository: ApprovalRepository | None = None,
    ) -> None:

        if default_expiry_minutes <= 0:
            raise ValueError(
                "default_expiry_minutes must be positive"
            )

        self.default_expiry_minutes = default_expiry_minutes
        self.repository = repository

        self._requests: dict[str, ApprovalRequest] = {}
        self._resolutions: dict[str, ApprovalResolution] = {}

        self._lock = RLock()

    def create_request(
        self,
        *,
        run_id: str,
        user_id: str,
        tool_call: ToolCall,
        reason: str,
        expiry_minutes: int | None = None,
    ) -> ApprovalRequest:
        """Create a pending approval request."""

        duration = (
            self.default_expiry_minutes
            if expiry_minutes is None
            else expiry_minutes
        )

        if duration <= 0:
            raise ValueError(
                "expiry_minutes must be positive"
            )

        created_at = utc_now()

        request = ApprovalRequest(
            run_id=run_id,
            user_id=user_id,
            tool_call=tool_call.model_copy(deep=True),
            reason=reason,
            created_at=created_at,
            expires_at=created_at + timedelta(minutes=duration),
        )

        if self.repository is not None:
            self.repository.create(request)
        else:
            with self._lock:
                self._requests[request.request_id] = request

        return request.model_copy(deep=True)

    def get_request(
        self,
        request_id: str,
    ) -> ApprovalRequest:
        """Retrieve an approval request."""

        if self.repository is not None:
            row = self.repository.get(request_id)

            if row is None:
                raise ApprovalNotFoundError(
                    f"Approval request not found: {request_id}"
                )

            return ApprovalRequest.model_validate(
                row["payload"]
            )

        with self._lock:
            request = self._get_request_unlocked(request_id)
            return request.model_copy(deep=True)

    def resolve(
        self,
        *,
        request_id: str,
        user_id: str,
        approve: bool,
    ) -> ApprovalResolution:
        """
        Resolve a pending approval request.

        user_id must come from an authenticated application
        identity, never from LLM-generated arguments.
        """

        if self.repository is not None:
            request = self.get_request(request_id)

            if request.user_id != user_id:
                raise ApprovalPermissionError(
                    "User is not authorized for this request"
                )

            row = self.repository.get(request_id)

            if row["status"] != ApprovalStatus.PENDING.value:
                raise ApprovalAlreadyResolvedError(
                    "Approval request already resolved"
                )

            if utc_now() >= request.expires_at:
                raise ApprovalExpiredError(
                    "Approval request has expired"
                )

            decision = (
                ApprovalStatus.APPROVED
                if approve
                else ApprovalStatus.DENIED
            )

            # Atomic conditional update enforces ownership,
            # expiration, and single resolution across workers.
            if not self.repository.resolve(
                request_id,
                user_id=user_id,
                decision=decision.value,
            ):
                raise ApprovalAlreadyResolvedError(
                    "Approval request could not be resolved "
                    "(concurrent change or expiration)"
                )

            return ApprovalResolution(
                request_id=request.request_id,
                call_id=request.tool_call.call_id,
                user_id=user_id,
                decision=decision,
            )

        with self._lock:
            request = self._get_request_unlocked(request_id)

            if request.user_id != user_id:
                raise ApprovalPermissionError(
                    "User is not authorized for this request"
                )

            if request_id in self._resolutions:
                raise ApprovalAlreadyResolvedError(
                    "Approval request already resolved"
                )

            if request.status != ApprovalStatus.PENDING:
                raise ApprovalAlreadyResolvedError(
                    "Approval request is not pending"
                )

            if utc_now() >= request.expires_at:
                raise ApprovalExpiredError(
                    "Approval request has expired"
                )

            decision = (
                ApprovalStatus.APPROVED
                if approve
                else ApprovalStatus.DENIED
            )

            resolution = ApprovalResolution(
                request_id=request.request_id,
                call_id=request.tool_call.call_id,
                user_id=user_id,
                decision=decision,
            )

            # Keep the creation-time request unchanged.
            # Store the resolution separately.
            self._resolutions[request_id] = resolution

            return resolution.model_copy(deep=True)

    def get_resolution(
        self,
        request_id: str,
    ) -> ApprovalResolution | None:
        """Retrieve an existing approval decision."""

        if self.repository is not None:
            row = self.repository.get(request_id)

            if row is None:
                raise ApprovalNotFoundError(
                    f"Approval request not found: {request_id}"
                )

            if row["status"] == ApprovalStatus.PENDING.value:
                return None

            if row["status"] not in (
                ApprovalStatus.APPROVED.value,
                ApprovalStatus.DENIED.value,
            ):
                raise ApprovalError(
                    "Invalid persisted approval status: "
                    f"{row['status']}"
                )

            request = ApprovalRequest.model_validate(
                row["payload"]
            )

            return ApprovalResolution(
                request_id=request_id,
                call_id=request.tool_call.call_id,
                user_id=request.user_id,
                decision=ApprovalStatus(row["status"]),
                resolved_at=row["updated_at"],
            )

        with self._lock:
            self._get_request_unlocked(request_id)

            resolution = self._resolutions.get(request_id)

            return (
                resolution.model_copy(deep=True)
                if resolution is not None
                else None
            )

    def validate_resume(
        self,
        *,
        request_id: str,
        run_id: str,
        user_id: str,
        tool_call: ToolCall,
    ) -> bool:
        """
        Verify that the exact approved tool call can resume.

        Validation checks:
            - Request exists
            - Same agent run
            - Same authenticated user
            - Same call ID
            - Same tool name
            - Same arguments
            - Request has not expired
            - Explicit approval exists

        Returns False for any failed validation.
        """

        if self.repository is not None:
            row = self.repository.get(request_id)

            if row is None:
                return False

            if row["status"] != ApprovalStatus.APPROVED.value:
                return False

            request = ApprovalRequest.model_validate(
                row["payload"]
            )

            if utc_now() >= request.expires_at:
                return False

            return (
                request.run_id == run_id
                and request.user_id == user_id
                and request.tool_call.call_id == tool_call.call_id
                and request.tool_call.tool_name == tool_call.tool_name
                and request.tool_call.arguments == tool_call.arguments
            )

        with self._lock:
            request = self._requests.get(request_id)

            if request is None:
                return False

            resolution = self._resolutions.get(request_id)

            if resolution is None:
                return False

            if resolution.decision != ApprovalStatus.APPROVED:
                return False

            if utc_now() >= request.expires_at:
                return False

            if request.run_id != run_id:
                return False

            if request.user_id != user_id:
                return False

            if resolution.user_id != user_id:
                return False

            if resolution.call_id != tool_call.call_id:
                return False

            original = request.tool_call

            if original.call_id != tool_call.call_id:
                return False

            if original.tool_name != tool_call.tool_name:
                return False

            if original.arguments != tool_call.arguments:
                return False

            return True

    def _get_request_unlocked(
        self,
        request_id: str,
    ) -> ApprovalRequest:
        """Internal lookup; caller must hold the lock."""

        request = self._requests.get(request_id)

        if request is None:
            raise ApprovalNotFoundError(
                f"Approval request not found: {request_id}"
            )

        return request

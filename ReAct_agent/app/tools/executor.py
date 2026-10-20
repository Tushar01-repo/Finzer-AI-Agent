"""Finzer tool execution with an approval-gated, single-use write path.

Read operations retain the Phase 4 interface. For write operations, the caller
must supply a verified application user ID, the original run/call IDs, and an
approval request ID issued by the same ApprovalManager instance.

Single-use protection is process-local by default. An optional persistent
repository reserves writes before dispatch and prevents automatic replay.
"""
from __future__ import annotations

import inspect
from functools import wraps
from threading import RLock
from typing import Any, Callable, TYPE_CHECKING

from pydantic import BaseModel

from app.agent.state import ToolCall
from app.tools.contracts import ToolOperation, ToolTransport
from app.tools.registry import require_tool_contract
from app.observability.logger import get_logger
from app.observability.tracing import trace_span
from app.observability.metrics import metrics

_observability_log = get_logger("finzer.tools.executor")


def _observe_tool_execution(func):
    """Trace all tool calls; count MCP calls without duplicating RAG metrics.

    DocumentRAGTool and NewsRAGTool already emit their own RAG metrics.
    The executor therefore does not record a second RAG measurement.
    Approval and replay checks remain exclusively inside execute().
    """
    @wraps(func)
    def wrapped(self, *, tool_name, arguments, run_id=None, user_id=None,
                call_id=None, approval_request_id=None):
        from contextlib import nullcontext

        is_local_rag = tool_name in ("document_rag", "news_rag")
        metric_context = nullcontext() if is_local_rag else metrics.time_operation("mcp")
        with trace_span("tool_execute", run_id=run_id, user_id=user_id):
            with metric_context:
                try:
                    result = func(
                        self, tool_name=tool_name, arguments=arguments,
                        run_id=run_id, user_id=user_id, call_id=call_id,
                        approval_request_id=approval_request_id,
                    )
                except Exception as exc:
                    _observability_log.error(
                        "tool_execution_exception",
                        error_type=type(exc).__name__,
                    )
                    raise
                _observability_log.info("tool_execution_completed")
                return result
    return wrapped

if TYPE_CHECKING:
    from app.governance.approval import ApprovalManager
    from app.persistence.repository import ToolExecutionRepository


class ToolExecutionError(RuntimeError):
    """A tool execution failed or returned an explicit error."""


class FinzerToolExecutor:
    def __init__(
        self,
        *,
        mcp_call: Callable[[str, str, dict[str, Any]], Any] | None = None,
        document_tool: Any | None = None,
        news_tool: Any | None = None,
        user_context_available: bool = False,
        approval_manager: ApprovalManager | None = None,
        execution_repository: ToolExecutionRepository | None = None,
    ) -> None:
        self.mcp_call = mcp_call
        self.document_tool = document_tool
        self.news_tool = news_tool
        self.user_context_available = user_context_available
        self.approval_manager = approval_manager
        self.execution_repository = execution_repository
        self._consumed_approval_ids: set[str] = set()
        self._authorization_lock = RLock()

    @_observe_tool_execution
    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        run_id: str | None = None,
        user_id: str | None = None,
        call_id: str | None = None,
        approval_request_id: str | None = None,
    ) -> Any:
        """Execute a registered tool after enforcing the execution gate.

        Write authorization is checked against an existing human approval,
        bound to the exact user, run, call ID, tool, and arguments. The
        approval is consumed before invoking the backend (fail closed).
        """
        contract = require_tool_contract(tool_name)
        if not isinstance(arguments, dict):
            raise TypeError("Tool arguments must be a dictionary")
        if contract.requires_user_context and not self.user_context_available:
            raise PermissionError(f"Authenticated user context required: {tool_name}")

        if contract.operation == ToolOperation.READ:
            return self._dispatch(tool_name, dict(arguments), contract)

        if contract.operation != ToolOperation.WRITE:
            raise PermissionError(f"Unsupported tool operation: {tool_name}")

        if not all((run_id, user_id, call_id, approval_request_id)):
            raise PermissionError(f"Write requires verified approval context: {tool_name}")
        if self.approval_manager is None:
            raise PermissionError("Approval manager is not configured")

        # Serialize approval consumption and invocation within this executor.
        # Marking an approval as used *before* dispatch prevents replay after
        # failures or ambiguous network outcomes.
        with self._authorization_lock:
            if approval_request_id in self._consumed_approval_ids:
                raise PermissionError("Approval has already been consumed")
            tool_call = ToolCall(
                call_id=call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
            )
            if not self.approval_manager.validate_resume(
                request_id=approval_request_id,
                run_id=run_id,
                user_id=user_id,
                tool_call=tool_call,
            ):
                raise PermissionError("Approval is invalid, expired, or does not match this call")
            if self.execution_repository is not None:
                # This is an atomic DB reservation. A conflicting call or
                # approval ID must fail closed, including after a restart.
                reserved = self.execution_repository.reserve(
                    run_id=run_id,
                    call_id=call_id,
                    tool_name=tool_name,
                    approval_request_id=approval_request_id,
                )
                if not reserved:
                    raise PermissionError(
                        "Tool call or approval already reserved or consumed"
                    )
            self._consumed_approval_ids.add(approval_request_id)

        if self.execution_repository is None:
            return self._dispatch(tool_name, dict(arguments), contract)

        try:
            result = self._dispatch(tool_name, dict(arguments), contract)
        except Exception as exc:
            # The external service might have committed the operation before
            # raising or timing out. Never automatically replay this call.
            self.execution_repository.finish(
                run_id=run_id,
                call_id=call_id,
                status="unknown",
                result={"error_type": type(exc).__name__},
            )
            raise

        # A failed DB write here leaves a reserved record. That is intentional:
        # an operator must reconcile rather than risking duplicate side effects.
        self.execution_repository.finish(
            run_id=run_id,
            call_id=call_id,
            status="succeeded",
            result=result,
        )
        return result

    def _dispatch(self, tool_name: str, arguments: dict[str, Any], contract: Any) -> Any:
        if contract.transport == ToolTransport.MCP:
            if self.mcp_call is None:
                raise ToolExecutionError("MCP connection is not configured")
            if not contract.server_name:
                raise ToolExecutionError(f"Missing MCP server for {tool_name}")
            # Diagnostic logging is intentionally restricted to this READ tool.
            # Avoid logging credentials or sensitive arguments from other tools.
            if tool_name == "search_mutual_funds":
                print(
                    "[MF MCP REQUEST]",
                    f"server={contract.server_name}",
                    f"arguments={arguments!r}",
                    flush=True,
                )

            result = self.mcp_call(contract.server_name, tool_name, arguments)

            if tool_name == "search_mutual_funds":
                print(
                    "[MF MCP RESPONSE]",
                    f"result={result!r}"[:2000],
                    flush=True,
                )
        elif contract.transport == ToolTransport.LOCAL:
            tool = self._local_tool(tool_name)
            inspect.signature(tool.execute).bind(**arguments)
            result = tool.execute(**arguments)
        else:
            raise ToolExecutionError(f"Unsupported transport: {contract.transport}")

        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
        if isinstance(result, dict) and (
            result.get("status") == "error" or result.get("isError") is True
        ):
            raise ToolExecutionError(f"{tool_name} failed: {result.get('error') or result}")
        return result

    def _local_tool(self, name: str) -> Any:
        if name == "document_rag":
            if self.document_tool is None:
                from app.tools.document_rag import DocumentRAGTool
                from app.tools.document_rag_backend import IngestionDocumentRAGBackend
                self.document_tool = DocumentRAGTool(IngestionDocumentRAGBackend())
            return self.document_tool
        if name == "news_rag":
            if self.news_tool is None:
                from app.tools.news_rag import NewsRAGTool
                from app.tools.news_rag_backend import IngestionNewsRAGBackend
                self.news_tool = NewsRAGTool(IngestionNewsRAGBackend())
            return self.news_tool
        raise ToolExecutionError(f"No local implementation for {name}")

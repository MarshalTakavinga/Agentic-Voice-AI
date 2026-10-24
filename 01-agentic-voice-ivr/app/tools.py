"""Tool registry: typed, authorized, audited actions the agent may take.

Guardrails are enforced here, in code, not in prompts:
  * requires_auth   - tool refuses unless the session has verified the caller
  * binds_customer  - customer_id argument must equal the session's verified customer
  * side_effect     - tool refuses unless the caller explicitly confirmed in this turn
This means a planner (rules today, an LLM in Milestone 2) cannot read another customer's
account or book an appointment without consent, however it is prompted.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.adapters.base import CustomerSystem, DomainError, UpstreamError
from app.adapters.mock import verify_pin
from app.observability import TOOL_CALLS, TOOL_LATENCY, log, tracer


class ToolContext(BaseModel):
    call_id: str
    authenticated: bool = False
    customer_id: str | None = None
    confirmed: bool = False


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AuthorizationError(Exception):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any, ToolContext], dict[str, Any]]
    requires_auth: bool = False
    binds_customer: bool = False
    side_effect: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        """JSON-schema tool definitions, shaped for LLM tool calling and for docs."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_model.model_json_schema(),
                "requires_auth": t.requires_auth,
                "side_effect": t.side_effect,
            }
            for t in self._tools.values()
        ]

    def call(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(tool=name, ok=False, error="unknown_tool")
        started = time.perf_counter()
        with tracer.start_as_current_span(f"tool.{name}") as span:
            span.set_attribute("ivr.call_id", ctx.call_id)
            try:
                result = self._execute(spec, args, ctx)
                outcome = "success"
            except ValidationError:
                result, outcome = (
                    ToolResult(tool=name, ok=False, error="invalid_arguments"),
                    "invalid_args",
                )
            except AuthorizationError as exc:
                result, outcome = ToolResult(tool=name, ok=False, error=str(exc)), "denied"
            except DomainError as exc:
                result, outcome = ToolResult(tool=name, ok=False, error=exc.code), "rejected"
            except UpstreamError:
                result, outcome = (
                    ToolResult(tool=name, ok=False, error="upstream_unavailable"),
                    "upstream_error",
                )
            elapsed = time.perf_counter() - started
            span.set_attribute("ivr.tool.outcome", outcome)
        TOOL_CALLS.labels(name, outcome).inc()
        TOOL_LATENCY.labels(name).observe(elapsed)
        log.info(
            "tool_call",
            tool=name,
            outcome=outcome,
            call_id=ctx.call_id,
            latency_ms=round(elapsed * 1000, 2),
        )
        return result

    @staticmethod
    def _execute(spec: ToolSpec, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if spec.requires_auth and not ctx.authenticated:
            raise AuthorizationError("authentication_required")
        if spec.side_effect and not ctx.confirmed:
            raise AuthorizationError("confirmation_required")
        params = spec.input_model.model_validate(args)
        if spec.binds_customer and getattr(params, "customer_id", None) != ctx.customer_id:
            raise AuthorizationError("customer_mismatch")
        return ToolResult(tool=spec.name, ok=True, data=spec.handler(params, ctx))


# ------------------------------------------------------------------ tool inputs


class VerifyCallerIn(BaseModel):
    account_number: str = Field(pattern=r"^\d{8}$")
    pin: str = Field(pattern=r"^\d{4}$")


class CustomerIn(BaseModel):
    customer_id: str = Field(pattern=r"^C\d{5}$")


class OutageIn(BaseModel):
    zip: str = Field(pattern=r"^\d{5}$")


class FindSlotsIn(CustomerIn):
    preferred_day: str | None = Field(default=None, max_length=12)


class BookVisitIn(CustomerIn):
    slot_id: str = Field(max_length=40)


class TransferIn(BaseModel):
    queue: Literal["billing", "tech_support", "general"]
    reason: Literal["caller_requested", "auth_failed", "no_match", "system_error"]
    context: dict[str, Any] = Field(default_factory=dict)


def build_registry(system: CustomerSystem) -> ToolRegistry:
    reg = ToolRegistry()

    def verify_caller(p: VerifyCallerIn, _ctx: ToolContext) -> dict[str, Any]:
        customer = system.get_customer_by_account(p.account_number)
        if customer is None or not verify_pin(customer, p.pin):
            return {"verified": False}  # identical response: no account enumeration
        return {
            "verified": True,
            "customer_id": customer.customer_id,
            "first_name": customer.first_name,
            "service_zip": customer.service_zip,
        }

    def get_balance(p: CustomerIn, _ctx: ToolContext) -> dict[str, Any]:
        c = system.get_customer(p.customer_id)
        return {"balance": f"${c.balance_cents / 100:,.2f}", "due_date": c.due_date.isoformat()}

    def check_outage(p: OutageIn, _ctx: ToolContext) -> dict[str, Any]:
        outage = system.get_outage(p.zip)
        if outage is None:
            return {"outage": False}
        return {
            "outage": True,
            "description": outage.description,
            "eta": outage.eta.isoformat() if outage.eta else None,
        }

    def find_slots(p: FindSlotsIn, _ctx: ToolContext) -> dict[str, Any]:
        c = system.get_customer(p.customer_id)
        slots = system.list_slots(c.service_zip, p.preferred_day)[:3]
        return {"slots": [{"slot_id": s.slot_id, "label": s.label} for s in slots]}

    def book_visit(p: BookVisitIn, _ctx: ToolContext) -> dict[str, Any]:
        appt = system.book(p.customer_id, p.slot_id)
        return {"confirmation": appt.confirmation, "label": appt.slot.label}

    def transfer(p: TransferIn, _ctx: ToolContext) -> dict[str, Any]:
        h = system.create_handoff(p.queue, p.reason, p.context)
        return {"handoff_id": h.handoff_id, "queue": h.queue, "reason": h.reason}

    reg.register(
        ToolSpec(
            "verify_caller",
            "Verify caller identity with account number and PIN.",
            VerifyCallerIn,
            verify_caller,
        )
    )
    reg.register(
        ToolSpec(
            "get_account_balance",
            "Current balance and due date.",
            CustomerIn,
            get_balance,
            requires_auth=True,
            binds_customer=True,
        )
    )
    reg.register(
        ToolSpec("check_service_outage", "Known outages for a ZIP code.", OutageIn, check_outage)
    )
    reg.register(
        ToolSpec(
            "find_technician_slots",
            "Open technician windows (max 3).",
            FindSlotsIn,
            find_slots,
            requires_auth=True,
            binds_customer=True,
        )
    )
    reg.register(
        ToolSpec(
            "book_technician_visit",
            "Book a technician window.",
            BookVisitIn,
            book_visit,
            requires_auth=True,
            binds_customer=True,
            side_effect=True,
        )
    )
    reg.register(
        ToolSpec(
            "transfer_to_agent",
            "Warm transfer with context to a human queue.",
            TransferIn,
            transfer,
        )
    )
    return reg

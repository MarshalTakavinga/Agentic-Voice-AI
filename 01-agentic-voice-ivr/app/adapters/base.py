"""Port for the enterprise systems the IVR depends on (CRM, billing, outage, workforce, ACD).

A real deployment implements this Protocol against Salesforce / ServiceNow / an outage API /
Amazon Connect or Genesys. The mock adapter implements it over synthetic JSON.
"""

from __future__ import annotations

from typing import Protocol

from app.domain import Appointment, AppointmentSlot, Customer, Handoff, Outage


class UpstreamError(Exception):
    """An enterprise dependency is unavailable or timed out."""


class DomainError(Exception):
    """A request was valid but the business rules rejected it."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CustomerSystem(Protocol):
    def ping(self) -> bool: ...

    def get_customer_by_account(self, account_number: str) -> Customer | None: ...

    def get_customer(self, customer_id: str) -> Customer: ...

    def get_outage(self, zip_code: str) -> Outage | None: ...

    def list_slots(self, zip_code: str, preferred_day: str | None) -> list[AppointmentSlot]: ...

    def book(
        self, customer_id: str, slot_id: str, idempotency_key: str | None = None
    ) -> Appointment:
        """Book a slot. A repeated ``idempotency_key`` returns the original appointment."""
        ...

    def create_handoff(self, queue: str, reason: str, context: dict) -> Handoff: ...

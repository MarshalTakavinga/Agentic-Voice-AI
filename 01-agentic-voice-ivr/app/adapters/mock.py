"""SIMULATED enterprise systems backed by synthetic JSON. No real customer data."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import threading
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path

from app.adapters.base import DomainError, UpstreamError
from app.domain import Appointment, AppointmentSlot, Customer, Handoff, Outage

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WINDOWS = [(8, 12), (12, 16)]
BOOKING_HORIZON_DAYS = 14


def hash_pin(pin: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), 100_000).hex()


def verify_pin(customer: Customer, pin: str) -> bool:
    return hmac.compare_digest(hash_pin(pin, customer.pin_salt), customer.pin_hash)


class MockCustomerSystem:
    def __init__(self, data_dir: Path, today: Callable[[], date] = date.today) -> None:
        customers = json.loads((data_dir / "customers.json").read_text())
        outages = json.loads((data_dir / "outages.json").read_text())
        self._customers = {c["customer_id"]: Customer(**c) for c in customers}
        self._by_account = {c.account_number: c for c in self._customers.values()}
        self._outages = {o["zip"]: Outage(**o) for o in outages}
        self._booked: dict[str, Appointment] = {}
        self._by_idempotency_key: dict[str, Appointment] = {}
        self._today = today
        self._lock = threading.Lock()
        self._seq = itertools.count(100001)

    def ping(self) -> bool:
        return bool(self._customers)

    def get_customer_by_account(self, account_number: str) -> Customer | None:
        return self._by_account.get(account_number)

    def get_customer(self, customer_id: str) -> Customer:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise DomainError("customer_not_found")
        if customer.simulate_fault:
            raise UpstreamError("billing system timeout (simulated)")
        return customer

    def get_outage(self, zip_code: str) -> Outage | None:
        outage = self._outages.get(zip_code)
        return outage if outage and outage.active else None

    def list_slots(self, zip_code: str, preferred_day: str | None) -> list[AppointmentSlot]:
        today = self._today()
        slots: list[AppointmentSlot] = []
        for offset in range(1, BOOKING_HORIZON_DAYS + 1):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5 or not _matches(day, today, preferred_day):
                continue
            for start_h, end_h in WINDOWS:
                slot_id = f"{zip_code}-{day.isoformat()}-{start_h:02d}"
                if slot_id in self._booked:
                    continue
                slots.append(
                    AppointmentSlot(
                        slot_id=slot_id,
                        start=datetime.combine(day, time(start_h)),
                        end=datetime.combine(day, time(end_h)),
                    )
                )
        return slots

    def book(
        self, customer_id: str, slot_id: str, idempotency_key: str | None = None
    ) -> Appointment:
        customer = self.get_customer(customer_id)
        with self._lock:
            replay = self._by_idempotency_key.get(idempotency_key or "")
            if replay is not None:
                if replay.customer_id != customer_id or replay.slot.slot_id != slot_id:
                    raise DomainError("idempotency_key_reused")
                return replay
            available = {s.slot_id: s for s in self.list_slots(customer.service_zip, None)}
            slot = available.get(slot_id)
            if slot is None:
                raise DomainError("slot_unavailable")
            appt = Appointment(
                confirmation=f"NW{next(self._seq)}", customer_id=customer_id, slot=slot
            )
            self._booked[slot_id] = appt
            if idempotency_key:
                self._by_idempotency_key[idempotency_key] = appt
            return appt

    def create_handoff(self, queue: str, reason: str, context: dict) -> Handoff:
        return Handoff(
            handoff_id=f"HO{next(self._seq)}", queue=queue, reason=reason, context=context
        )


def _matches(day: date, today: date, preferred: str | None) -> bool:
    if preferred in (None, "earliest"):
        return True
    if preferred == "today":
        return day == today
    if preferred == "tomorrow":
        return day == today + timedelta(days=1)
    if preferred in WEEKDAYS:
        # The next occurrence of that weekday only.
        return WEEKDAYS[day.weekday()] == preferred and (day - today).days <= 7
    return True

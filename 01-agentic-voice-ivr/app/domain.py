"""Domain models shared by adapters and tools."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class Customer(BaseModel):
    customer_id: str
    account_number: str
    first_name: str
    last_name: str
    service_zip: str
    plan: str
    balance_cents: int
    due_date: date
    pin_salt: str
    pin_hash: str
    simulate_fault: bool = False  # synthetic-data hook for failure-path testing


class Outage(BaseModel):
    zip: str
    active: bool
    description: str
    eta: datetime | None = None


class AppointmentSlot(BaseModel):
    slot_id: str
    start: datetime
    end: datetime

    @property
    def label(self) -> str:
        day = f"{self.start:%A, %B} {self.start.day}"
        return f"{day} between {_hour(self.start)} and {_hour(self.end)}"


class Appointment(BaseModel):
    confirmation: str
    customer_id: str
    slot: AppointmentSlot


class Handoff(BaseModel):
    handoff_id: str
    queue: str
    reason: str
    context: dict


def _hour(dt: datetime) -> str:
    if dt.hour == 12:
        return "noon"
    hour = dt.hour % 12 or 12
    return f"{hour} {'AM' if dt.hour < 12 else 'PM'}"


def spoken_time(dt: datetime) -> str:
    return f"{_hour(dt)} on {dt:%A}"

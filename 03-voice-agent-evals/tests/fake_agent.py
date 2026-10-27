"""A tiny agent implementing the turn API, with switchable bugs.

The evaluator is only trustworthy if it catches broken agents. Each bug here is a failure class
the framework claims to detect; tests turn them on one at a time and check the right signal
fires (policy violation, disclosure, failed expectation, target error, latency).
"""

from __future__ import annotations

import asyncio
import re
import uuid

from fastapi import FastAPI, Header, HTTPException

CATALOG = [
    {"name": "verify_caller", "requires_auth": False, "side_effect": False},
    {"name": "get_account_balance", "requires_auth": True, "side_effect": False},
    {"name": "book_technician_visit", "requires_auth": True, "side_effect": True},
    {"name": "transfer_to_agent", "requires_auth": False, "side_effect": False},
]
ACCOUNTS = {"10000001": ("1234", "Ava", "$89.99")}


def create_app(
    bugs: frozenset[str] = frozenset(), slow_ms: int = 0, key: str = "test-key"
) -> FastAPI:
    app = FastAPI()
    calls: dict[str, dict] = {}

    def check(x_api_key: str) -> None:
        if x_api_key != key:
            raise HTTPException(401)

    def view(c: dict) -> dict:
        return {
            "call_id": c["id"],
            "status": c["status"],
            "reply": c["reply"],
            "turn": c["turn"],
            "intent": c.get("intent"),
            "nlu_source": "rules",
            "expecting": c.get("expecting"),
            "authenticated": c["auth"],
            "awaiting_confirmation": c.get("pending") is not None,
            "completed_tasks": c["tasks"],
            "handoff": c.get("handoff"),
        }

    def tool(c: dict, name: str, ok: bool = True) -> None:
        c["events"].append(
            {"turn": c["turn"], "tool": name, "ok": ok, "error": None if ok else "denied"}
        )

    @app.get("/v1/tools")
    def tools(x_api_key: str = Header(default="")) -> list[dict]:
        check(x_api_key)
        return CATALOG

    @app.post("/v1/calls", status_code=201)
    def start(x_api_key: str = Header(default="")) -> dict:
        check(x_api_key)
        cid = f"CA{uuid.uuid4().hex}"
        calls[cid] = {
            "id": cid,
            "status": "in_progress",
            "reply": "How can I help?",
            "turn": 0,
            "auth": False,
            "tasks": [],
            "events": [],
            "account": None,
        }
        return view(calls[cid])

    @app.get("/v1/calls/{cid}")
    def get(cid: str, x_api_key: str = Header(default="")) -> dict:
        check(x_api_key)
        return {**view(calls[cid]), "events": calls[cid]["events"]}

    @app.get("/metrics")
    def metrics() -> str:
        raise HTTPException(404)

    @app.post("/v1/calls/{cid}/turns")
    async def turn(cid: str, body: dict, x_api_key: str = Header(default="")) -> dict:
        check(x_api_key)
        c = calls.get(cid)
        if c is None:
            raise HTTPException(404)
        if c["status"] != "in_progress":
            raise HTTPException(409)
        if slow_ms:
            await asyncio.sleep(slow_ms / 1000)
        text = str(body.get("text", "")).lower().strip()
        if "boom" in text and "error_500" in bugs:
            raise HTTPException(500)
        c["turn"] += 1
        digits = "".join(re.findall(r"\d", text))
        if "uncatalogued" in bugs:
            tool(c, "secret_tool")
        if "agent" in text:
            tool(c, "transfer_to_agent")
            c.update(
                status="escalated",
                reply="Connecting you to a specialist.",
                handoff={"reason": "caller_requested", "queue": "general"},
            )
        elif c.get("pending") and text.startswith("yes"):
            tool(c, "book_technician_visit")
            c["tasks"].append("schedule_technician")
            c.update(pending=None, reply="Booked. Your confirmation number is 42.")
        elif "book" in text:
            if not c["auth"] and "no_auth_check" not in bugs:
                c.update(intent="book", expecting="account_number", reply="Your account number?")
            elif "skip_consent" in bugs:
                tool(c, "book_technician_visit")
                c["tasks"].append("schedule_technician")
                c["reply"] = "Booked. Your confirmation number is 42."
            else:
                c.update(
                    pending="slot", reply="Monday at 8 AM is open. Would you like me to book it?"
                )
        elif "balance" in text:
            if "no_auth_check" in bugs:
                tool(c, "get_account_balance")
                c["tasks"].append("check_balance")
                c["reply"] = "Your balance is $89.99."
            else:
                c.update(intent="balance", expecting="account_number", reply="Your account number?")
        elif c.get("expecting") == "account_number" and len(digits) == 8:
            c.update(account=digits, expecting="pin", reply="And your PIN?")
        elif c.get("expecting") == "pin" and len(digits) == 4:
            ok = ACCOUNTS.get(c["account"] or "", ("",))[0] == digits
            tool(c, "verify_caller", ok)
            if ok:
                _, name, bal = ACCOUNTS[c["account"]]
                c.update(auth=True, expecting=None)
                if c.get("intent") == "book" and "skip_consent" in bugs:
                    tool(c, "book_technician_visit")
                    c["tasks"].append("schedule_technician")
                    c["reply"] = f"Thanks {name}. Booked. Your confirmation number is 42."
                elif c.get("intent") == "book":
                    c.update(
                        pending="slot",
                        reply=f"Thanks {name}. Monday at 8 AM is open. "
                        "Would you like me to book it?",
                    )
                else:
                    tool(c, "get_account_balance")
                    c["tasks"].append("check_balance")
                    c["reply"] = f"Thanks {name}. Your balance is {bal}."
            else:
                c.update(
                    expecting="account_number", reply="That didn't match. Your account number?"
                )
        elif text in ("bye", "no that's all"):
            c.update(status="completed", reply="Goodbye.")
        else:
            c["reply"] = "Sorry, I didn't catch that."
        if "leak" in bugs:
            c["reply"] += " By the way, the other account owes $42.50."
        return view(c)

    return app


def buggy(*names: str):
    """App factory with the given bugs switched on."""
    return lambda: create_app(frozenset(names))


def skip_consent_app() -> FastAPI:
    return create_app(frozenset({"skip_consent"}))


def unsafe_app() -> FastAPI:
    return create_app(frozenset({"skip_consent", "no_auth_check"}))

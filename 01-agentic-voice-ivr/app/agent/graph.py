"""The IVR agent: a LangGraph state machine that runs once per caller turn.

    START -> understand -> route --+-> authenticate --+-> fulfill --+-> END
                                   |                  +-> escalate  +-> escalate
                                   +-> plan (LLM, only when rules can't map the request)
                                   |     +-> authenticate / fulfill / escalate / END
                                   +-> fulfill / confirm / escalate / reprompt / help / end

State is returned to the caller after every turn and persisted by the session store, so the
graph itself is stateless and any replica can serve the next turn.
"""

from __future__ import annotations

import operator
import time
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.domain import spoken_time
from app.nlu import NLUProvider
from app.observability import CALL_OUTCOMES, TURN_LATENCY, TURNS, tracer
from app.tools import ToolContext, ToolRegistry, ToolResult

if TYPE_CHECKING:
    from app.agent.planner import Planner

AUTH_REQUIRED = frozenset({"check_balance", "schedule_technician"})
BUSINESS_INTENTS = frozenset({"check_balance", "check_outage", "schedule_technician"})
QUEUE_BY_INTENT = {
    "check_balance": "billing",
    "check_outage": "tech_support",
    "schedule_technician": "tech_support",
}
SLOT_PROMPTS = {
    "account_number": "your eight digit account number",
    "pin": "your four digit PIN",
    "zip": "the five digit ZIP code where you're having trouble",
}
MENU = "I can check your balance, check for outages in your area, or schedule a technician visit."
GREETING = (
    "Thanks for calling Northwind Fiber. You're speaking with an automated assistant. "
    f"{MENU} How can I help?"
)
ANYTHING_ELSE = "Is there anything else I can help you with?"


class IVRState(TypedDict, total=False):
    call_id: str
    channel: str
    utterance: str
    nlu: dict[str, Any]
    active_intent: str | None
    slots: dict[str, str]
    expecting: str | None
    authenticated: bool
    customer_id: str | None
    customer_first_name: str | None
    auth_attempts: int
    no_match_count: int
    pending_action: dict[str, Any] | None
    force_escalate: bool
    response: str
    status: str
    turn: int
    completed_tasks: list[str]
    handoff: dict[str, Any] | None
    events: Annotated[list[dict[str, Any]], operator.add]
    # Planner (Milestone 2)
    last_reply: str
    planner_turns: int
    planner_trace: dict[str, Any] | None
    planner_outcome: str | None
    queued_tasks: list[str]
    continue_queue: bool


def _say(state: IVRState, text: str) -> str:
    return f"{state.get('response', '')} {text}".strip()


def _digits(value: str) -> str:
    """Speak identifiers digit by digit, the way TTS callers expect."""
    return " ".join(value)


class IVRAgent:
    def __init__(
        self,
        nlu: NLUProvider,
        tools: ToolRegistry,
        settings: Settings,
        planner: Planner | None = None,
    ) -> None:
        self.nlu = nlu
        self.tools = tools
        self.settings = settings
        self.planner = planner
        self.graph = self._build()

    # ------------------------------------------------------------ public API
    def new_state(self, call_id: str, channel: str) -> IVRState:
        return IVRState(
            call_id=call_id,
            channel=channel,
            slots={},
            active_intent=None,
            expecting=None,
            authenticated=False,
            customer_id=None,
            customer_first_name=None,
            auth_attempts=0,
            no_match_count=0,
            pending_action=None,
            force_escalate=False,
            response=GREETING,
            status="in_progress",
            turn=0,
            completed_tasks=[],
            handoff=None,
            events=[],
            last_reply=GREETING,
            planner_turns=0,
            planner_trace=None,
            planner_outcome=None,
            queued_tasks=[],
            continue_queue=False,
        )

    def handle_turn(self, state: IVRState, utterance: str) -> IVRState:
        started = time.perf_counter()
        with tracer.start_as_current_span("ivr.turn") as span:
            span.set_attribute("ivr.call_id", state["call_id"])
            span.set_attribute("ivr.turn", state.get("turn", 0) + 1)
            result: IVRState = self.graph.invoke({**state, "utterance": utterance[:500]})
            span.set_attribute("ivr.intent", result["nlu"]["intent"])
            span.set_attribute("ivr.status", result["status"])
        result.pop("utterance", None)  # never persist raw caller speech in session state
        result["last_reply"] = result["response"]
        TURN_LATENCY.observe(time.perf_counter() - started)
        TURNS.labels(result["nlu"]["intent"], state.get("channel", "api")).inc()
        if result["status"] != "in_progress":
            CALL_OUTCOMES.labels(result["status"]).inc()
        return result

    # ------------------------------------------------------------ graph wiring
    def _build(self):  # noqa: ANN202 - CompiledStateGraph generic is noisy
        g = StateGraph(IVRState)
        for name in (
            "understand",
            "authenticate",
            "fulfill",
            "confirm",
            "escalate",
            "reprompt",
            "help",
            "end",
            "plan",
        ):
            g.add_node(name, getattr(self, f"_{name}"))
        g.add_edge(START, "understand")
        g.add_conditional_edges("understand", self._route)
        g.add_conditional_edges("authenticate", self._after_auth)
        g.add_conditional_edges("fulfill", self._after_action)
        g.add_conditional_edges("confirm", self._after_action)
        g.add_conditional_edges("plan", self._after_plan)
        for terminal in ("escalate", "reprompt", "help", "end"):
            g.add_edge(terminal, END)
        return g.compile()

    def _route(self, s: IVRState) -> str:
        intent = s["nlu"]["intent"]
        if intent == "agent":
            return "escalate"
        if intent == "goodbye":
            return "end"
        if self._wants_planner(s):
            return "plan"
        if intent == "no_match":
            return "escalate" if s["no_match_count"] >= self.settings.max_no_match else "reprompt"
        if intent in ("affirm", "deny") and s.get("pending_action"):
            return "confirm"
        if intent == "help" or not s.get("active_intent"):
            return "help"
        if s["active_intent"] in AUTH_REQUIRED and not s.get("authenticated"):
            return "authenticate"
        return "fulfill"

    @staticmethod
    def _after_auth(s: IVRState) -> str:
        if s.get("force_escalate"):
            return "escalate"
        return "fulfill" if s.get("authenticated") else END

    def _after_action(self, s: IVRState) -> str:
        if s.get("force_escalate"):
            return "escalate"
        if s.get("continue_queue"):  # a queued task from a multi-part request starts now
            return self._task_entry(s)
        return END

    def _wants_planner(self, s: IVRState) -> bool:
        """Call the LLM only when the rules couldn't map the request to a goal: never while
        collecting identifiers, and never once the per-call or daily budget is used up."""
        if self.planner is None or s.get("expecting") or s.get("pending_action"):
            return False
        intent = s["nlu"]["intent"]
        unmapped = intent == "no_match" or (intent == "provide_info" and not s.get("active_intent"))
        return unmapped and self.planner.allowed(s)

    @staticmethod
    def _task_entry(s: IVRState) -> str:
        if s.get("active_intent") in AUTH_REQUIRED and not s.get("authenticated"):
            return "authenticate"
        return "fulfill"

    def _after_plan(self, s: IVRState) -> str:
        outcome = s.get("planner_outcome")
        if outcome == "transfer":
            return "escalate"
        if outcome == "start_tasks":
            return self._task_entry(s)
        if outcome == "fallback":
            if (
                s["nlu"]["intent"] == "no_match"
                and s["no_match_count"] >= self.settings.max_no_match
            ):
                return "escalate"
            return "reprompt" if s["nlu"]["intent"] == "no_match" else "help"
        return END

    # ------------------------------------------------------------ helpers
    def _call(
        self, s: IVRState, tool: str, args: dict[str, Any], confirmed: bool = False
    ) -> tuple[ToolResult, dict[str, Any]]:
        ctx = ToolContext(
            call_id=s["call_id"],
            authenticated=bool(s.get("authenticated")),
            customer_id=s.get("customer_id"),
            confirmed=confirmed,
        )
        result = self.tools.call(tool, args, ctx)
        # Audit event: which tool, when, outcome. Arguments are deliberately not recorded.
        event = {"turn": s.get("turn", 0), "tool": tool, "ok": result.ok, "error": result.error}
        return result, event

    def _task_done(self, s: IVRState, task: str, text: str, events: list[dict]) -> dict:
        update = {
            "active_intent": None,
            "expecting": None,
            "events": events,
            "completed_tasks": [*s.get("completed_tasks", []), task],
            "response": _say(s, f"{text} {ANYTHING_ELSE}"),
        }
        queue = [t for t in s.get("queued_tasks", []) if t != task]
        if queue:  # multi-part request: move straight on to the next task
            update.update(
                active_intent=queue[0],
                queued_tasks=queue[1:],
                continue_queue=True,
                response=_say(s, text),
            )
        return update

    @staticmethod
    def _system_error(s: IVRState, events: list[dict]) -> dict:
        return {
            "events": events,
            "force_escalate": True,
            "pending_action": None,
            "response": _say(s, "I'm having trouble reaching that system right now."),
        }

    # ------------------------------------------------------------ nodes
    def _understand(self, s: IVRState) -> dict:
        nlu = self.nlu.parse(s.get("utterance", ""), expecting=s.get("expecting"))
        update: dict[str, Any] = {
            "nlu": nlu.model_dump(),
            "slots": {**s.get("slots", {}), **nlu.entities},
            "response": "",
            "turn": s.get("turn", 0) + 1,
            "force_escalate": False,
            "continue_queue": False,
            "planner_trace": None,
            "planner_outcome": None,
            "no_match_count": s.get("no_match_count", 0) + 1 if nlu.intent == "no_match" else 0,
        }
        if nlu.intent in BUSINESS_INTENTS and nlu.intent != s.get("active_intent"):
            update["active_intent"] = nlu.intent  # caller changed goals mid-conversation
            update["queued_tasks"] = []
        if nlu.intent not in ("affirm", "deny"):
            update["pending_action"] = None  # an offer only survives a direct yes/no
        return update

    def _authenticate(self, s: IVRState) -> dict:
        slots = dict(s["slots"])
        if "account_number" not in slots:
            return {
                "expecting": "account_number",
                "response": _say(
                    s,
                    "First I need to verify your account. Please say or enter "
                    f"{SLOT_PROMPTS['account_number']}.",
                ),
            }
        if "pin" not in slots:
            return {
                "expecting": "pin",
                "response": _say(s, f"Thanks. Now please say or enter {SLOT_PROMPTS['pin']}."),
            }
        # Credentials leave state the moment they are used.
        args = {"account_number": slots.pop("account_number"), "pin": slots.pop("pin")}
        result, event = self._call(s, "verify_caller", args)
        if not result.ok:
            return {**self._system_error(s, [event]), "slots": slots}
        if result.data.get("verified"):
            slots["service_zip"] = result.data["service_zip"]
            first = result.data["first_name"]
            return {
                "authenticated": True,
                "customer_id": result.data["customer_id"],
                "customer_first_name": first,
                "slots": slots,
                "expecting": None,
                "events": [event],
                "response": _say(s, f"Thanks, {first}, you're verified."),
            }
        attempts = s.get("auth_attempts", 0) + 1
        if attempts >= self.settings.max_auth_attempts:
            return {
                "auth_attempts": attempts,
                "slots": slots,
                "events": [event],
                "force_escalate": True,
                "response": _say(s, "I wasn't able to verify that account."),
            }
        return {
            "auth_attempts": attempts,
            "slots": slots,
            "events": [event],
            "expecting": "account_number",
            "response": _say(
                s,
                "That account number and PIN didn't match our records. Let's try again. "
                f"Please say {SLOT_PROMPTS['account_number']}.",
            ),
        }

    def _fulfill(self, s: IVRState) -> dict:
        return getattr(self, f"_do_{s['active_intent']}")(s)

    def _do_check_balance(self, s: IVRState) -> dict:
        result, event = self._call(s, "get_account_balance", {"customer_id": s["customer_id"]})
        if not result.ok:
            return self._system_error(s, [event])
        due = datetime.fromisoformat(result.data["due_date"])
        return self._task_done(
            s,
            "check_balance",
            f"Your current balance is {result.data['balance']}, due on {due:%B} {due.day}.",
            [event],
        )

    def _do_check_outage(self, s: IVRState) -> dict:
        zip_code = s["slots"].get("zip") or s["slots"].get("service_zip")
        if not zip_code:
            return {
                "expecting": "zip",
                "response": _say(s, f"Please say or enter {SLOT_PROMPTS['zip']}."),
            }
        result, event = self._call(s, "check_service_outage", {"zip": zip_code})
        if not result.ok:
            return self._system_error(s, [event])
        if result.data["outage"]:
            text = (
                f"Yes, there's a known service outage affecting ZIP code {_digits(zip_code)}. "
                f"{result.data['description']}."
            )
            if result.data.get("eta"):
                text += (
                    " Our estimated restoration time is "
                    f"{spoken_time(datetime.fromisoformat(result.data['eta']))}."
                )
        else:
            text = (
                f"I'm not seeing any reported outage for ZIP code {_digits(zip_code)}. "
                "If your service still isn't working, I can schedule a technician."
            )
        return self._task_done(s, "check_outage", text, [event])

    def _do_schedule_technician(self, s: IVRState) -> dict:
        slots = dict(s["slots"])
        result, event = self._call(
            s,
            "find_technician_slots",
            {"customer_id": s["customer_id"], "preferred_day": slots.get("preferred_day")},
        )
        if not result.ok:
            return self._system_error(s, [event])
        if not result.data["slots"]:
            slots.pop("preferred_day", None)
            return {
                "slots": slots,
                "expecting": None,
                "events": [event],
                "response": _say(
                    s,
                    "I don't see any open appointments for that day. You can name another "
                    "weekday, or say agent to speak with someone.",
                ),
            }
        offer = result.data["slots"][0]
        return {
            "events": [event],
            "expecting": None,
            "pending_action": {
                "tool": "book_technician_visit",
                "args": {"customer_id": s["customer_id"], "slot_id": offer["slot_id"]},
                "label": offer["label"],
            },
            "response": _say(
                s,
                f"The earliest available technician visit is "
                f"{offer['label']}. Would you like me to book it?",
            ),
        }

    def _confirm(self, s: IVRState) -> dict:
        pending = s["pending_action"]
        if s["nlu"]["intent"] == "deny":
            slots = {k: v for k, v in s["slots"].items() if k != "preferred_day"}
            return {
                "pending_action": None,
                "slots": slots,
                "response": _say(
                    s,
                    "Okay, I won't book that. You can name a different day, like Thursday, "
                    "or say agent to speak with someone.",
                ),
            }
        result, event = self._call(s, pending["tool"], pending["args"], confirmed=True)
        if not result.ok:
            return self._system_error(s, [event])
        done = self._task_done(
            s,
            "schedule_technician",
            f"You're all set for {result.data['label']}. Your confirmation "
            f"number is {_digits(result.data['confirmation'])}.",
            [event],
        )
        return {**done, "pending_action": None}

    def _escalate(self, s: IVRState) -> dict:
        if s["nlu"]["intent"] == "agent" or s.get("planner_outcome") == "transfer":
            reason, prefix = "caller_requested", "Sure."
        elif s.get("auth_attempts", 0) >= self.settings.max_auth_attempts:
            reason, prefix = "auth_failed", ""
        elif s.get("no_match_count", 0) >= self.settings.max_no_match:
            reason, prefix = "no_match", "Sorry, I'm having trouble understanding."
        else:
            reason, prefix = "system_error", ""
        queue = QUEUE_BY_INTENT.get(s.get("active_intent") or "", "general")
        # Warm-transfer context: what an agent needs so the caller never repeats themselves.
        context = {
            "intent": s.get("active_intent"),
            "authenticated": s.get("authenticated"),
            "customer_id": s.get("customer_id"),
            "turns": s.get("turn"),
            "completed_tasks": s.get("completed_tasks", []),
        }
        result, event = self._call(
            s, "transfer_to_agent", {"queue": queue, "reason": reason, "context": context}
        )
        handoff = (
            result.data if result.ok else {"queue": queue, "reason": reason, "handoff_id": None}
        )
        return {
            "status": "escalated",
            "handoff": handoff,
            "expecting": None,
            "events": [event],
            "response": _say(
                s,
                f"{prefix} Let me connect you with a specialist. I've passed "
                "along what we've covered so you won't have to repeat "
                "yourself.".strip(),
            ),
        }

    def _plan(self, s: IVRState) -> dict:
        result = self.planner.plan(s, s.get("utterance", ""))
        update: dict[str, Any] = {
            "planner_turns": s.get("planner_turns", 0) + 1,
            "planner_trace": result.trace,
            "planner_outcome": result.action,
            "events": result.events,
        }
        if result.action != "fallback":
            update["no_match_count"] = 0  # the planner understood the caller
        if result.action == "start_tasks":
            slots = dict(s.get("slots", {}))
            if result.preferred_day:
                slots["preferred_day"] = result.preferred_day
            update.update(active_intent=result.tasks[0], queued_tasks=result.tasks[1:], slots=slots)
        elif result.action == "reply":
            done = [t for t in result.completed if t not in s.get("completed_tasks", [])]
            update.update(
                response=_say(s, result.reply),
                completed_tasks=[*s.get("completed_tasks", []), *done],
            )
        return update

    def _reprompt(self, s: IVRState) -> dict:
        expecting = s.get("expecting")
        ask = (
            f"Please say or enter {SLOT_PROMPTS[expecting]}."
            if expecting
            else f"{MENU} What would you like to do?"
        )
        return {"response": _say(s, f"Sorry, I didn't catch that. {ask}")}

    def _help(self, s: IVRState) -> dict:
        expecting = s.get("expecting")
        tail = (
            f" To continue, please say {SLOT_PROMPTS[expecting]}."
            if expecting
            else " What would you like to do?"
        )
        return {"response": _say(s, MENU + tail)}

    @staticmethod
    def _end(s: IVRState) -> dict:
        return {
            "status": "completed",
            "expecting": None,
            "response": _say(s, "Thanks for calling Northwind Fiber. Goodbye."),
        }

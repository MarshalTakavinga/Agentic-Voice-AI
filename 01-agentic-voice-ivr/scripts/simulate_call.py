"""Talk to the IVR from your terminal, as a caller would.

python scripts/simulate_call.py                       # in-process, no server needed
python scripts/simulate_call.py --url http://localhost:8000 --api-key change-me-local-only
python scripts/simulate_call.py --script "balance" "10000001" "1234" "bye"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class LocalClient:
    def __init__(self) -> None:
        from app.config import Settings
        from app.main import create_app
        from app.service import public_view

        self._service = create_app(Settings(log_level="WARNING")).state.service
        self._view = public_view

    def start(self) -> dict:
        return self._view(self._service.start_call("simulator"))

    def turn(self, call_id: str, text: str) -> dict:
        return self._view(self._service.take_turn(call_id, text))


class HttpClient:
    def __init__(self, url: str, api_key: str) -> None:
        import httpx

        self._http = httpx.Client(base_url=url, headers={"X-API-Key": api_key}, timeout=10)

    def start(self) -> dict:
        resp = self._http.post("/v1/calls", json={"channel": "simulator"})
        resp.raise_for_status()
        return resp.json()

    def turn(self, call_id: str, text: str) -> dict:
        resp = self._http.post(f"/v1/calls/{call_id}/turns", json={"text": text})
        resp.raise_for_status()
        return resp.json()


def show(view: dict) -> None:
    meta = f"[intent={view['intent']} expecting={view['expecting']} auth={view['authenticated']}]"
    print(f"\nIVR: {view['reply']}\n     {meta if view['turn'] else ''}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", help="API base URL; omit to run in-process")
    parser.add_argument("--api-key", default="change-me-local-only")
    parser.add_argument("--script", nargs="+", help="utterances to send non-interactively")
    args = parser.parse_args()

    client = HttpClient(args.url, args.api_key) if args.url else LocalClient()
    view = client.start()
    show(view)
    utterances = iter(args.script) if args.script else None
    while view["status"] == "in_progress":
        if utterances is not None:
            text = next(utterances, None)
            if text is None:
                break
            print(f"\nYOU: {text}")
        else:
            try:
                text = input("\nYOU: ")
            except (EOFError, KeyboardInterrupt):
                break
        view = client.turn(view["call_id"], text)
        show(view)
    if view.get("handoff"):
        print(
            f"\n--> transferred to queue '{view['handoff']['queue']}' "
            f"(reason: {view['handoff']['reason']})"
        )
    print(f"\nCall {view['call_id']} ended with status: {view['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

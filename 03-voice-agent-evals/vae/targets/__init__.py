"""Targets: the voice agents under test, reached through a small turn-based contract.

See docs/target-contract.md for the contract any agent can implement to be evaluated.
"""

from vae.targets.base import CallEndedError, Target, TargetError, ToolEvent, ToolInfo, TurnView
from vae.targets.http import HttpTarget

__all__ = [
    "CallEndedError",
    "HttpTarget",
    "Target",
    "TargetError",
    "ToolEvent",
    "ToolInfo",
    "TurnView",
]

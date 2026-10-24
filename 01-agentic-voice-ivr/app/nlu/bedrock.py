"""Amazon Bedrock intent classification via the Converse API with forced tool use.

Status: SIMULATED in this repo. Unit-tested against a stub client that returns the documented
Converse response shape; not yet run against a live Bedrock account. Requires `pip install
.[bedrock]`, AWS credentials, and IVR_BEDROCK_MODEL_ID set to a model enabled in your account.
"""

from __future__ import annotations

from typing import Any

from app.nlu.base import INTENTS
from app.nlu.llm import SYSTEM_PROMPT, GuardedLLMNLU, classification_prompt

_TOOL = {
    "toolSpec": {
        "name": "record_intent",
        "description": "Record the caller's intent.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "enum": list(INTENTS)},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["intent", "confidence"],
            }
        },
    }
}


class BedrockNLU(GuardedLLMNLU):
    name = "bedrock"

    def __init__(
        self, model_id: str, region: str, min_confidence: float = 0.5, client: Any = None
    ) -> None:
        super().__init__(min_confidence)
        if not model_id and client is None:
            raise ValueError("IVR_BEDROCK_MODEL_ID is required for the bedrock provider")
        self._model_id = model_id
        if client is None:
            import boto3  # optional dependency

            client = boto3.client("bedrock-runtime", region_name=region)
        self._client = client

    def classify(self, utterance: str, expecting: str | None) -> dict[str, Any]:
        resp = self._client.converse(
            modelId=self._model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {"role": "user", "content": [{"text": classification_prompt(utterance, expecting)}]}
            ],
            toolConfig={"tools": [_TOOL], "toolChoice": {"tool": {"name": "record_intent"}}},
            inferenceConfig={"maxTokens": 100, "temperature": 0},
        )
        for block in resp["output"]["message"]["content"]:
            if "toolUse" in block:
                return block["toolUse"]["input"]
        raise ValueError("model did not call record_intent")

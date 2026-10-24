from app.config import Settings
from app.nlu.base import NLUProvider, NLUResult
from app.nlu.rules import RulesNLU

__all__ = ["NLUProvider", "NLUResult", "RulesNLU", "build_nlu"]


def build_nlu(settings: Settings) -> NLUProvider:
    if settings.nlu_provider == "openai_compatible":
        from app.nlu.llm import OpenAICompatibleNLU

        return OpenAICompatibleNLU(
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_api_key.get_secret_value(),
            settings.llm_timeout_s,
            settings.llm_min_confidence,
        )
    if settings.nlu_provider == "bedrock":
        from app.nlu.bedrock import BedrockNLU

        return BedrockNLU(
            settings.bedrock_model_id, settings.aws_region, settings.llm_min_confidence
        )
    return RulesNLU()

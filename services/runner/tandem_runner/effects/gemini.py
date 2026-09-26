"""Gemini structured-output calls through LiteLLM. Stubs until M2; no API call is made."""

from pydantic import JsonValue

from tandem_core.stage import EffectRequest


def structured(request: EffectRequest) -> JsonValue:
    return {
        "dominion_position": "Stub brief: no LLM was called.",
        "georgia_position": "Stub brief: no LLM was called.",
        "mediator_summary": "Stub brief: no LLM was called.",
        "shareable": [],
        "cited_fields": [],
    }


def disambiguate(request: EffectRequest) -> JsonValue:
    return {"choice": None, "stub": True}

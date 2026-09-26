"""Nominatim search. Stub until M2 (1 req/s, User-Agent with contact email, cached)."""

from pydantic import JsonValue

from tandem_core.stage import EffectRequest


def search(request: EffectRequest) -> JsonValue:
    return {"results": [], "stub": True}

"""OpenStreetMap Overpass queries. Stub until M2 (public endpoint, backoff, cached)."""

from pydantic import JsonValue

from tandem_core.stage import EffectRequest


def query(request: EffectRequest) -> JsonValue:
    return {"elements": [], "stub": True}

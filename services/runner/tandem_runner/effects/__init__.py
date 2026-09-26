"""Effect executors: the only code that touches files, the network, or the LLM.

Each executor takes an EffectRequest and returns a JSON value. The runner caches the
result by the request's SHA-256 key, so executors run at most once per distinct request.
All executors are stubs until M1/M2.
"""

from collections.abc import Callable, Mapping

from pydantic import JsonValue

from tandem_core.stage import EffectRequest
from tandem_runner.effects import files, gemini, nominatim, overpass

Executor = Callable[[EffectRequest], JsonValue]

EXECUTORS: Mapping[str, Executor] = {
    "read_pdf_text": files.read_pdf_text,
    "read_xlsx": files.read_xlsx,
    "overpass": overpass.query,
    "nominatim": nominatim.search,
    "llm_disambiguate": gemini.disambiguate,
    "llm_structured": gemini.structured,
}

"""File reads. Stubs: they return empty content until the parsers land in M1."""

from pydantic import JsonValue

from tandem_core.stage import EffectRequest


def read_pdf_text(request: EffectRequest) -> JsonValue:
    return {"path": request.params["path"], "pages": [], "stub": True}


def read_xlsx(request: EffectRequest) -> JsonValue:
    return {"path": request.params["path"], "sheets": {}, "stub": True}

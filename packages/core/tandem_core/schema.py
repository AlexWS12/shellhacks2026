"""JSON Schema for the contract, as text. Pure: callers decide where to write it."""

import json
from typing import Any

from pydantic import BaseModel, TypeAdapter

from tandem_core import models

MODELS: tuple[type[BaseModel], ...] = (
    models.Provenance,
    models.Location,
    models.Endpoint,
    models.Project,
    models.Overlap,
    models.Check,
    models.ReferenceSet,
    models.ReferenceResult,
    models.CostAssumption,
    models.CostEstimate,
    models.Brief,
    models.Opportunity,
    models.StageState,
    models.RunState,
)

DRAFT = "http://json-schema.org/draft-07/schema#"


def _normalize(node: Any) -> Any:
    """Shape Pydantic's output for json-schema-to-typescript.

    - Drop per-property titles, which json2ts turns into one type alias per field.
      Model titles (on $defs entries and the root) are kept; they name the types.
    - Express tuples as draft-07 `items: [...]` instead of 2020-12 `prefixItems`,
      which json2ts does not support.
    """
    if isinstance(node, list):
        return [_normalize(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: _normalize(v) for k, v in node.items()}
    if "prefixItems" in out:
        out["items"] = out.pop("prefixItems")
    if isinstance(out.get("properties"), dict):
        out["properties"] = {
            name: {k: v for k, v in prop.items() if k != "title"}
            for name, prop in out["properties"].items()
        }
    return out


def _dump(schema: dict[str, Any]) -> str:
    schema = {"$schema": DRAFT, **_normalize(schema)}
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def json_schemas() -> dict[str, str]:
    """Map of schema file name to canonical JSON text, one per model plus the Event union."""
    out = {f"{m.__name__}.json": _dump(m.model_json_schema(mode="serialization")) for m in MODELS}
    event = TypeAdapter(models.Event).json_schema(mode="serialization")
    event["title"] = "Event"
    out["Event.json"] = _dump(event)
    return dict(sorted(out.items()))

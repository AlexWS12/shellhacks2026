"""effect_cache: effect results keyed by the SHA-256 of the canonical request JSON."""

import json
import sqlite3

from pydantic import JsonValue

from tandem_core.stage import EffectRequest, canonical_json


class EffectCache:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def get(self, request: EffectRequest) -> tuple[bool, JsonValue]:
        """(found, response). A cached response may itself be JSON null."""
        row = self._db.execute(
            "SELECT response_json FROM effect_cache WHERE hash = ?", (request.key,)
        ).fetchone()
        if row is None:
            return False, None
        value: JsonValue = json.loads(row[0])
        return True, value

    def put(self, request: EffectRequest, response: JsonValue) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO effect_cache (hash, request_json, response_json) "
            "VALUES (?, ?, ?)",
            (
                request.key,
                canonical_json(request.model_dump(mode="json")),
                canonical_json(response),
            ),
        )
        self._db.commit()

import asyncio
import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from tandem_api.main import create_app
from tandem_api.settings import Settings
from tandem_core.models import Event, RunStarted, RunStartedPayload, RunState
from tandem_core.reduce import fold
from tandem_runner.events import EventLog, open_db

ROOT = Path(__file__).resolve().parents[3]
RECORDED = sorted((ROOT / "data" / "runs").glob("*.jsonl"))
EVENT: TypeAdapter[Event] = TypeAdapter(Event)


def read_jsonl(path: Path) -> list[Event]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EVENT.validate_json(line) for line in lines if line]


def parse_sse(body: str) -> list[tuple[str | None, Event]]:
    """(id, event) for each SSE message with data; comments are skipped."""
    out = []
    for block in body.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(":") or ": " not in line:
                continue
            key, value = line.split(": ", 1)
            fields[key] = value
        if "data" in fields:
            out.append((fields.get("id"), EVENT.validate_json(fields["data"])))
    return out


class Sleeps:
    """Records requested delays; yields to the loop without actually waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        await asyncio.sleep(0.001)


def make_settings(tmp_path: Path, runs_dir: Path | None = None, **kw: Any) -> Settings:
    return Settings(
        config_path=ROOT / "pipeline.yaml",
        db_path=tmp_path / "api.db",
        runs_dir=runs_dir or ROOT / "data" / "runs",
        **kw,
    )


@pytest.fixture
def sleeps() -> Sleeps:
    return Sleeps()


@pytest.fixture
def client(tmp_path: Path, sleeps: Sleeps) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path, sleep=sleeps))) as c:
        yield c


def stream(client: TestClient, url: str, **kw: Any) -> list[tuple[str | None, Event]]:
    with client.stream("GET", url, **kw) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return parse_sse(response.read().decode())


def start(client: TestClient, body: dict[str, Any] | None = None) -> str:
    response = client.post("/runs", json=body)
    assert response.status_code == 202, response.text
    run_id: str = response.json()["run_id"]
    return run_id


# --- Live runs ----------------------------------------------------------------------


def test_started_run_streams_to_run_completed(client: TestClient) -> None:
    run_id = start(client)
    messages = stream(client, f"/runs/{run_id}/events")
    events = [e for _, e in messages]
    assert events[0].type == "run.started"
    assert events[-1].type == "run.completed"
    last = events[-1]
    assert last.type == "run.completed" and last.payload.status == "completed"
    assert [e.seq for e in events] == list(range(len(events)))
    assert [i for i, _ in messages] == [str(e.seq) for e in events]
    assert {e.run_id for e in events} == {run_id}


def test_state_is_the_fold_of_the_stream(client: TestClient) -> None:
    run_id = start(client)
    events = [e for _, e in stream(client, f"/runs/{run_id}/events")]
    state = RunState.model_validate(client.get(f"/runs/{run_id}/state").json())
    assert state == fold(events)
    assert state.status == "completed"
    assert [o.overlap.id for o in state.opportunities] == ["DESC_3~GPC_2"]


def test_resume_from_seq_and_last_event_id(client: TestClient) -> None:
    run_id = start(client)
    full = [e for _, e in stream(client, f"/runs/{run_id}/events")]
    tail = [e for _, e in stream(client, f"/runs/{run_id}/events?from_seq=10")]
    assert tail == full[10:]
    resumed = stream(client, f"/runs/{run_id}/events", headers={"Last-Event-ID": "19"})
    assert [e for _, e in resumed] == full[20:]


def test_resuming_past_the_end_of_a_finished_run_is_204(client: TestClient) -> None:
    run_id = start(client)
    full = stream(client, f"/runs/{run_id}/events")
    response = client.get(f"/runs/{run_id}/events?from_seq={len(full)}")
    assert response.status_code == 204


def test_list_runs_includes_recorded_and_new_runs(client: TestClient) -> None:
    recorded_ids = {read_jsonl(p)[0].run_id for p in RECORDED}
    run_id = start(client)
    stream(client, f"/runs/{run_id}/events")
    runs = client.get("/runs").json()
    assert runs[0]["run_id"] == run_id
    assert runs[0]["status"] == "completed"
    assert runs[0]["totals"]["stage.completed"] == 9
    assert recorded_ids == {r["run_id"] for r in runs if r["recorded"]}
    assert runs[0]["recorded"] is False


def test_cors_allows_the_web_app(client: TestClient) -> None:
    response = client.get("/runs", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    blocked = client.get("/runs", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


def test_run_overrides(client: TestClient) -> None:
    run_id = start(client, {"today": "2031-01-01", "sponsors": ["GPC"]})
    first = stream(client, f"/runs/{run_id}/events")[0][1]
    assert first.type == "run.started"
    assert first.payload.today.isoformat() == "2031-01-01"

    run_id = start(client, {"sources": {"reference_xlsx": "Projects_Overlaps.xlsx"}})
    assert stream(client, f"/runs/{run_id}/events")[-1][1].type == "run.completed"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"sources": {"desc_pdf": "../../pipeline.yaml"}}, "inside data/sources"),
        ({"sources": {"desc_pdf": "missing.pdf"}}, "not found"),
        ({"sources": {"nope": "Projects_Overlaps.xlsx"}}, "unknown source"),
    ],
)
def test_bad_overrides_are_rejected(client: TestClient, body: dict[str, Any], message: str) -> None:
    response = client.post("/runs", json=body)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/nope/events").status_code == 404
    assert client.get("/runs/nope/state").status_code == 404


# --- Replay -------------------------------------------------------------------------


@pytest.mark.parametrize("path", RECORDED, ids=lambda p: p.name)
def test_replay_of_stored_run_is_identical(client: TestClient, path: Path) -> None:
    stored = read_jsonl(path)
    replayed = [e for _, e in stream(client, f"/runs/{stored[0].run_id}/events?replay=1&speed=10")]
    assert [e.payload for e in replayed] == [e.payload for e in stored]
    assert replayed == stored


def test_replay_spacing_is_divided_by_speed_and_capped(tmp_path: Path, sleeps: Sleeps) -> None:
    template = read_jsonl(RECORDED[0])
    start_ts = template[0].ts
    offsets = [0.0, 0.5, 30.5, 33.5]  # gaps of 0.5 s, 30 s, 3 s
    picked = [template[0], template[1], template[2], template[-1]]
    synthetic = [
        e.model_copy(update={"run_id": "slow", "seq": i, "ts": start_ts + timedelta(seconds=t)})
        for i, (e, t) in enumerate(zip(picked, offsets, strict=True))
    ]
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    lines = [EVENT.dump_json(e).decode() for e in synthetic]
    (runs_dir / "slow.jsonl").write_text("\n".join(lines) + "\n")

    settings = make_settings(tmp_path, runs_dir=runs_dir, sleep=sleeps)
    with TestClient(create_app(settings)) as client:
        events = [e for _, e in stream(client, "/runs/slow/events?replay=1&speed=2")]
    assert events == synthetic
    assert sleeps.calls == pytest.approx([0.25, 2.0, 1.5])


def test_replay_rejects_unfinished_runs_and_bad_speed(tmp_path: Path, client: TestClient) -> None:
    events = EventLog(open_db(tmp_path / "api.db"))
    events.start_run("running", "hash", "2026-09-26")
    template = read_jsonl(RECORDED[0])[0]
    assert isinstance(template, RunStarted)
    events.append("running", RunStarted, RunStartedPayload.model_validate(template.payload))
    assert client.get("/runs/running/events?replay=1").status_code == 409
    finished = read_jsonl(RECORDED[0])[0].run_id
    assert client.get(f"/runs/{finished}/events?replay=1&speed=11").status_code == 422
    assert client.get(f"/runs/{finished}/events?replay=1&speed=0.5").status_code == 422


def test_not_yet_implemented_endpoints(client: TestClient) -> None:
    run_id = read_jsonl(RECORDED[0])[0].run_id
    assert client.get(f"/runs/{run_id}/export.xlsx").status_code == 501
    assert client.get(f"/runs/{run_id}/diff/{run_id}").status_code == 501


def test_recorded_runs_are_valid() -> None:
    assert len(RECORDED) >= 3
    for path in RECORDED:
        events = read_jsonl(path)
        assert events[0].type == "run.started" and events[-1].type == "run.completed"
        assert [e.seq for e in events] == list(range(len(events)))
        assert json.loads(path.read_text().splitlines()[-1])["payload"]["status"] == "completed"

"""events -> RunState. Pure; mirrors apps/web/lib/reducer.ts.

Opportunities are derived here from overlaps in the default order (distance, then
gap) and carry any brief written for them. No event carries rank_and_cost's cost
estimates yet, so `cost_estimate` stays None in the folded state.
"""

from collections.abc import Iterable

from tandem_core.models import Brief, Endpoint, Event, Opportunity, Overlap, RunState, StageState

INITIAL = RunState(
    run_id="",
    status="running",
    stages={},
    projects={},
    checks=(),
    overlaps={},
    reference_results=(),
    opportunities=(),
    totals={},
)


def reduce(state: RunState, event: Event) -> RunState:
    match event.type:
        case "run.started":
            return INITIAL.model_copy(update={"run_id": event.run_id})
        case "stage.started":
            stage = StageState(status="running", counts={}, used_fallback=None)
            return _update(state, stages={**state.stages, event.payload.stage_id: stage})
        case "stage.completed":
            done = event.payload
            stage = StageState(
                status="completed", counts=done.counts, used_fallback=done.used_fallback
            )
            return _update(state, stages={**state.stages, done.stage_id: stage})
        case "record.extracted":
            return _update(state, projects={**state.projects, event.payload.id: event.payload})
        case "endpoint.located":
            located_ep = event.payload
            project = state.projects.get(located_ep.project_id)
            if project is None:
                return state
            endpoints = _replace_endpoint(project.endpoints, located_ep.endpoint)
            located = project.model_copy(update={"endpoints": endpoints})
            return _update(state, projects={**state.projects, project.id: located})
        case "check.raised":
            return _update(state, checks=(*state.checks, event.payload))
        case "overlap.found":
            overlaps = {**state.overlaps, event.payload.id: event.payload}
            return _update(state, overlaps=overlaps, opportunities=_rank(overlaps, _briefs(state)))
        case "reference.tested":
            return _update(state, reference_results=(*state.reference_results, event.payload))
        case "brief.written":
            briefs = {**_briefs(state), event.payload.overlap_id: event.payload.brief}
            return _update(state, opportunities=_rank(state.overlaps, briefs))
        case "run.completed":
            return _update(state, status=event.payload.status, totals=event.payload.totals)


def fold(events: Iterable[Event], state: RunState = INITIAL) -> RunState:
    for event in events:
        state = reduce(state, event)
    return state


def _update(state: RunState, **fields: object) -> RunState:
    return state.model_copy(update=fields)


def _replace_endpoint(endpoints: tuple[Endpoint, ...], new: Endpoint) -> tuple[Endpoint, ...]:
    if any(e.raw_name == new.raw_name for e in endpoints):
        return tuple(new if e.raw_name == new.raw_name else e for e in endpoints)
    return (*endpoints, new)


def _briefs(state: RunState) -> dict[str, Brief]:
    return {o.overlap.id: o.brief for o in state.opportunities if o.brief is not None}


def _rank(overlaps: dict[str, Overlap], briefs: dict[str, Brief]) -> tuple[Opportunity, ...]:
    ordered = sorted(overlaps.values(), key=lambda o: (o.distance_mi, o.gap_days, o.id))
    return tuple(
        Opportunity(
            overlap=o,
            rank=i,
            windows_overlap=o.windows_overlap,
            cost_estimate=None,
            brief=briefs.get(o.id),
        )
        for i, o in enumerate(ordered, start=1)
    )

/**
 * events -> UiState. Pure; mirrors packages/core/tandem_core/reduce.py.
 *
 * The only place that turns events into state. Parity with the Python reducer is
 * enforced by reducer.test.ts and test_reducer_parity.py, which fold the same logs
 * and compare against the same packages/contracts/fixtures/reducer/*.state.json.
 */
import type { Event } from "@tandem/contracts/ts/Event";
import type {
  Brief,
  Endpoint,
  Opportunity,
  Overlap,
  RunState,
  StageState,
} from "@tandem/contracts/ts/RunState";

export type UiState = RunState;

export const INITIAL: UiState = {
  run_id: "",
  status: "running",
  stages: {},
  projects: {},
  checks: [],
  overlaps: {},
  reference_results: [],
  opportunities: [],
  totals: {},
};

export function reduce(state: UiState, event: Event): UiState {
  switch (event.type) {
    case "run.started":
      return { ...INITIAL, run_id: event.run_id };
    case "stage.started": {
      const stage: StageState = { status: "running", counts: {}, used_fallback: null };
      return { ...state, stages: { ...state.stages, [event.payload.stage_id]: stage } };
    }
    case "stage.completed": {
      const done = event.payload;
      const stage: StageState = {
        status: "completed",
        counts: done.counts,
        used_fallback: done.used_fallback,
      };
      return { ...state, stages: { ...state.stages, [done.stage_id]: stage } };
    }
    case "record.extracted":
      return { ...state, projects: { ...state.projects, [event.payload.id]: event.payload } };
    case "endpoint.located": {
      const { project_id, endpoint } = event.payload;
      const project = state.projects[project_id];
      if (project === undefined) return state;
      const located = { ...project, endpoints: replaceEndpoint(project.endpoints, endpoint) };
      return { ...state, projects: { ...state.projects, [project.id]: located } };
    }
    case "check.raised":
      return { ...state, checks: [...state.checks, event.payload] };
    case "overlap.found": {
      const overlaps = { ...state.overlaps, [event.payload.id]: event.payload };
      return { ...state, overlaps, opportunities: rank(overlaps, briefs(state)) };
    }
    case "reference.tested":
      return { ...state, reference_results: [...state.reference_results, event.payload] };
    case "brief.written": {
      const next = { ...briefs(state), [event.payload.overlap_id]: event.payload.brief };
      return { ...state, opportunities: rank(state.overlaps, next) };
    }
    case "run.completed":
      return { ...state, status: event.payload.status, totals: event.payload.totals };
    default: {
      const unreachable: never = event;
      return unreachable;
    }
  }
}

export function fold(events: Iterable<Event>, state: UiState = INITIAL): UiState {
  for (const event of events) state = reduce(state, event);
  return state;
}

function replaceEndpoint(endpoints: Endpoint[], next: Endpoint): Endpoint[] {
  if (endpoints.some((e) => e.raw_name === next.raw_name)) {
    return endpoints.map((e) => (e.raw_name === next.raw_name ? next : e));
  }
  return [...endpoints, next];
}

function briefs(state: UiState): Record<string, Brief> {
  const out: Record<string, Brief> = {};
  for (const o of state.opportunities) if (o.brief !== null) out[o.overlap.id] = o.brief;
  return out;
}

/** Default order (FR-10): distance, then gap, then id; same key as reduce.py `_rank`. */
function rank(overlaps: Record<string, Overlap>, byOverlap: Record<string, Brief>): Opportunity[] {
  const ordered = Object.values(overlaps).sort(
    (a, b) =>
      a.distance_mi - b.distance_mi || a.gap_days - b.gap_days || compareCodePoints(a.id, b.id),
  );
  return ordered.map((o, i) => ({
    overlap: o,
    rank: i + 1,
    windows_overlap: o.windows_overlap,
    cost_estimate: null,
    brief: byOverlap[o.id] ?? null,
  }));
}

/** Python's str ordering (code points), not localeCompare. */
function compareCodePoints(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

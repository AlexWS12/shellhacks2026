import type { UiState } from "@/lib/reducer";

export function OpportunityList({ state }: { state: UiState }) {
  const projectName = (id: string) => state.projects[id]?.name ?? id;

  return (
    <aside className="col right" aria-label="Coordination opportunities">
      <h2>Coordination opportunities</h2>
      <div className="stats">
        <div>
          <b>{Object.keys(state.projects).length}</b>projects
        </div>
        <div>
          <b>{state.opportunities.length}</b>under 25 mi
        </div>
        <div>
          <b>{state.checks.length}</b>data checks
        </div>
      </div>
      {state.opportunities.length === 0 ? (
        <p className="empty">Pairs under 25 miles apart appear here, closest first.</p>
      ) : (
        <ol className="opps">
          {state.opportunities.map(({ overlap, rank, brief }) => (
            <li key={overlap.id} className="opp">
              <span className="rk">{rank}</span>
              <div>
                <div className="pair">
                  <span className="desc">{projectName(overlap.a)}</span>
                  <span className="gpc">{projectName(overlap.b)}</span>
                </div>
                <span className="pill">{overlap.distance_mi.toFixed(2)} mi</span>
                <span className="pill time">{overlap.gap_days} days apart</span>
                {brief && <span className="pill brief">brief: {brief.source}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}

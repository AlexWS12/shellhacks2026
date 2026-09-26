import type { UiState } from "@/lib/reducer";
import { stageRows } from "@/lib/selectors";

const STATE_TEXT = {
  pending: "waiting",
  running: "working",
  completed: "done",
  failed: "failed",
} as const;

function countsText(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([name, n]) => `${n} ${name}`)
    .join(", ");
}

export function PipelinePanel({ state }: { state: UiState }) {
  const rows = stageRows(state);
  const done = rows.filter((r) => r.state.status === "completed").length;

  return (
    <aside className="col left" aria-label="Pipeline">
      <h2>Pipeline</h2>
      <p className="ticker">
        {state.run_id === ""
          ? "Not started."
          : `Run ${state.run_id.slice(0, 8)} · ${state.status} · ${done} of ${rows.length} stages done`}
      </p>

      <h3>Stages</h3>
      {rows.length === 0 ? (
        <p className="empty">Stages appear here as the run reports them.</p>
      ) : (
        <ol className="stages" aria-live="polite">
          {rows.map(({ id, label, state: stage }) => (
            <li key={id} className={stage.status}>
              <span className="dot" aria-hidden="true" />
              <span>
                {label}
                {Object.keys(stage.counts).length > 0 && (
                  <span className="detail">{countsText(stage.counts)}</span>
                )}
                {stage.used_fallback && (
                  <span className="detail fallback">fallback: {stage.used_fallback}</span>
                )}
              </span>
              <span className="state">{STATE_TEXT[stage.status]}</span>
            </li>
          ))}
        </ol>
      )}

      <h3>Check against the sponsor&apos;s answers</h3>
      {state.reference_results.length === 0 ? (
        <p className="empty">Runs after the overlap engine.</p>
      ) : (
        <table className="reft">
          <thead>
            <tr>
              <th scope="col">Pair</th>
              <th scope="col">Miles</th>
              <th scope="col">Days</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {state.reference_results.map((r) => (
              <tr key={r.pair.join("~")}>
                <td>{r.pair.join(" · ")}</td>
                <td>
                  {r.actual_mi ?? "–"} / {r.expected_mi}
                </td>
                <td>
                  {r.actual_days ?? "–"} / {r.expected_days}
                </td>
                <td className={r.passed ? "pass" : "fail"}>{r.passed ? "pass" : "fail"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Data checks</h3>
      {state.checks.length === 0 ? (
        <p className="empty">The validator lists problems it finds in the source files here.</p>
      ) : (
        state.checks.map((c, i) => (
          <div key={i} className={`chk ${c.severity}`}>
            <b>
              {c.rule_id} · {c.subject}
            </b>
            <span>{c.message}</span>
          </div>
        ))
      )}
    </aside>
  );
}

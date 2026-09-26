"use client";

import { useRunStream } from "@/lib/useRunStream";

import { MapView } from "./MapView";
import { OpportunityList } from "./OpportunityList";
import { PipelinePanel } from "./PipelinePanel";
import { ThemeToggle, useTheme } from "./ThemeToggle";

const CONNECTION_TEXT = {
  idle: "",
  starting: "Connecting…",
  live: "Running",
  replaying: "Replaying recorded run",
  done: "",
  error: "",
} as const;

export function Shell() {
  const { state, connection, error, run, replay } = useRunStream();
  const theme = useTheme();
  const busy = connection === "starting" || connection === "live" || connection === "replaying";

  return (
    <div className="app">
      <header>
        <h1>Tandem</h1>
        <span className="tag">Finds where neighboring utilities plan to build close together</span>
        <span className="spacer" />
        <span className={`conn${error ? " error" : ""}`} role="status" aria-live="polite">
          {error ?? CONNECTION_TEXT[connection]}
        </span>
        <ThemeToggle theme={theme} />
        <button type="button" onClick={replay} disabled={busy}>
          Replay recorded run
        </button>
        <button type="button" className="primary" onClick={run} disabled={busy}>
          Run pipeline
        </button>
      </header>
      <div className="main">
        <PipelinePanel state={state} />
        <MapView
          theme={theme.effective}
          showIntro={state.run_id === "" && !busy}
          onRun={run}
          onReplay={replay}
        />
        <OpportunityList state={state} />
      </div>
    </div>
  );
}

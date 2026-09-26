/**
 * Pure reads over UiState for components. Filters (sponsor set, confidence, hide
 * finished) and sorting arrive with the opportunity list in M3; they will live here.
 */
import type { StageState } from "@tandem/contracts/ts/RunState";

import type { UiState } from "./reducer";

export interface StageRow {
  id: string;
  label: string;
  state: StageState;
}

/** Stages in the order they started (object keys keep insertion order). */
export function stageRows(state: UiState): StageRow[] {
  return Object.entries(state.stages).map(([id, stage]) => ({
    id,
    label: stageLabel(id),
    state: stage,
  }));
}

export function stageLabel(id: string): string {
  const words = id.split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

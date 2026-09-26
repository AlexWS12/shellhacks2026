/**
 * TypeScript half of the reducer parity test; packages/core/tests/test_reducer_parity.py
 * is the other half. Both fold the same logs against the same committed fixtures.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { Event } from "@tandem/contracts/ts/Event";
import { describe, expect, it } from "vitest";

import { fold, INITIAL, reduce } from "./reducer";
import { stageLabel, stageRows } from "./selectors";

const ROOT = join(import.meta.dirname, "..", "..", "..");
const FIXTURES = join(ROOT, "packages", "contracts", "fixtures", "reducer");
const RUNS = join(ROOT, "data", "runs");

const logs: Record<string, string> = { "edge-cases": join(FIXTURES, "edge-cases.jsonl") };
for (const file of readdirSync(RUNS).filter((f) => f.endsWith(".jsonl")).sort()) {
  logs[file.replace(/\.jsonl$/, "")] = join(RUNS, file);
}

function readEvents(path: string): Event[] {
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => JSON.parse(line) as Event);
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === "object") {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

describe("reducer parity with tandem_core.reduce.fold", () => {
  it("has a fixture for every log", () => {
    const states = readdirSync(FIXTURES).filter((f) => f.endsWith(".state.json"));
    expect(states.sort()).toEqual(Object.keys(logs).map((n) => `${n}.state.json`).sort());
  });

  it.each(Object.keys(logs))("%s folds to the shared fixture", (name) => {
    const expected: unknown = JSON.parse(
      readFileSync(join(FIXTURES, `${name}.state.json`), "utf8"),
    );
    expect(fold(readEvents(logs[name]))).toEqual(expected);
  });
});

describe("reducer", () => {
  it("never mutates its input", () => {
    const events = readEvents(logs["edge-cases"]).map(deepFreeze);
    let state = deepFreeze(INITIAL);
    for (const event of events) state = deepFreeze(reduce(state, event));
    expect(state.status).toBe("failed");
  });

  it("lists stages in start order with labels", () => {
    const state = fold(readEvents(logs["edge-cases"]));
    expect(stageRows(state).map((r) => [r.label, r.state.status])).toEqual([
      ["Extract desc", "completed"],
      ["Locate", "completed"],
      ["Reference test", "running"],
    ]);
    expect(stageLabel("rank_and_cost")).toBe("Rank and cost");
  });
});

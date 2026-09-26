"use client";

import type { Event } from "@tandem/contracts/ts/Event";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { API_URL, REPLAY_SPEED } from "./config";
import { INITIAL, reduce, type UiState } from "./reducer";

/** Connection status is view state; everything about the run comes from reduce(). */
export type Connection = "idle" | "starting" | "live" | "replaying" | "done" | "error";

interface RunSummary {
  run_id: string;
  status: string;
  recorded: boolean;
}

export interface RunStream {
  state: UiState;
  connection: Connection;
  error: string | null;
  run: () => Promise<void>;
  replay: () => Promise<void>;
}

export function useRunStream(): RunStream {
  const [state, dispatch] = useReducer(reduce, INITIAL);
  const [connection, setConnection] = useState<Connection>("idle");
  const [error, setError] = useState<string | null>(null);
  const source = useRef<EventSource | null>(null);

  const fail = useCallback((message: string) => {
    source.current?.close();
    setConnection("error");
    setError(message);
  }, []);

  const subscribe = useCallback(
    (url: string, mode: "live" | "replaying") => {
      source.current?.close();
      let nextSeq = 0;
      const es = new EventSource(url);
      source.current = es;
      setConnection(mode);
      setError(null);
      es.onmessage = (message: MessageEvent<string>) => {
        const event = JSON.parse(message.data) as Event;
        if (event.seq < nextSeq) return; // already applied before a reconnect
        nextSeq = event.seq + 1;
        dispatch(event);
        if (event.type === "run.completed") {
          es.close();
          setConnection("done");
        }
      };
      es.onerror = () => {
        // While CONNECTING the browser retries with Last-Event-ID on its own.
        if (es.readyState === EventSource.CLOSED) fail("Lost the event stream from the API.");
      };
    },
    [fail],
  );

  const run = useCallback(async () => {
    setConnection("starting");
    try {
      const response = await fetch(`${API_URL}/runs`, { method: "POST" });
      if (!response.ok) throw new Error(`POST /runs returned ${response.status}`);
      const { run_id } = (await response.json()) as { run_id: string };
      subscribe(`${API_URL}/runs/${run_id}/events`, "live");
    } catch (e) {
      fail(`Could not start a run: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [fail, subscribe]);

  const replay = useCallback(async () => {
    setConnection("starting");
    try {
      const response = await fetch(`${API_URL}/runs`);
      if (!response.ok) throw new Error(`GET /runs returned ${response.status}`);
      const runs = (await response.json()) as RunSummary[];
      const latest = runs.find((r) => r.recorded && r.status !== "running");
      if (latest === undefined) throw new Error("no recorded run in data/runs/");
      subscribe(
        `${API_URL}/runs/${latest.run_id}/events?replay=1&speed=${REPLAY_SPEED}`,
        "replaying",
      );
    } catch (e) {
      fail(`Could not replay: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [fail, subscribe]);

  useEffect(() => () => source.current?.close(), []);

  return { state, connection, error, run, replay };
}

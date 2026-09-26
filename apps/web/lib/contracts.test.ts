import type { Event } from "@tandem/contracts/ts/Event";
import { describe, expectTypeOf, it } from "vitest";

type EventOf<T extends Event["type"]> = Extract<Event, { type: T }>;

// Type-only: these assertions are checked by `tsc` (make lint); at runtime they are no-ops.
describe("generated Event contract", () => {
  it("is a union over exactly the ten event types", () => {
    expectTypeOf<Event["type"]>().toEqualTypeOf<
      | "run.started"
      | "stage.started"
      | "stage.completed"
      | "record.extracted"
      | "endpoint.located"
      | "check.raised"
      | "overlap.found"
      | "reference.tested"
      | "brief.written"
      | "run.completed"
    >();
  });

  it("carries the shared envelope on every event", () => {
    expectTypeOf<Event>().toHaveProperty("run_id").toEqualTypeOf<string>();
    expectTypeOf<Event>().toHaveProperty("seq").toEqualTypeOf<number>();
    expectTypeOf<Event>().toHaveProperty("ts").toEqualTypeOf<string>();
    expectTypeOf<Event>().toHaveProperty("fixture").toEqualTypeOf<boolean>();
  });

  it("narrows payloads by type", () => {
    expectTypeOf<EventOf<"overlap.found">["payload"]["distance_mi"]>().toEqualTypeOf<number>();
    expectTypeOf<EventOf<"record.extracted">["payload"]["center"]>().toEqualTypeOf<
      [number, number] | null
    >();
    expectTypeOf<EventOf<"brief.written">["payload"]["brief"]["source"]>().toEqualTypeOf<
      "llm" | "template"
    >();
  });
});

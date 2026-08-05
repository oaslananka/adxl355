import { describe, expect, it } from "vitest";

import {
  MEASUREMENT_SETTLE_MS,
  enterMeasurementAndSettle,
} from "../examples/common.mjs";

describe("bounded Linux examples", () => {
  it("enters measurement before the bounded settle delay", async () => {
    const events: string[] = [];
    const device = {
      async setPowerMode(mode: number): Promise<void> {
        events.push(`mode:${mode}`);
      },
    };
    const sleep = async (milliseconds: number): Promise<void> => {
      events.push(`sleep:${milliseconds}`);
    };

    await enterMeasurementAndSettle(device, 0, sleep);

    expect(MEASUREMENT_SETTLE_MS).toBe(20);
    expect(events).toEqual(["mode:0", "sleep:20"]);
  });
});

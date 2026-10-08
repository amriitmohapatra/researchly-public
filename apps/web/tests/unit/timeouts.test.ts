import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ANALYZE_TIMEOUT_MS } from "@/lib/engine";

// Regression: the browser waited 120 s while the engine may take 300 s, so a
// whole-thesis upload (~110 s on Cloud Run) was abandoned just before it finished.
describe("browser and engine timeouts", () => {
  const spec = readFileSync(join(__dirname, "../../../../services/engine/deploy/cloudrun.service.yaml"), "utf8");
  const engineSeconds = Number(/^\s{6}timeoutSeconds:\s*(\d+)/m.exec(spec)?.[1]);

  it("the browser waits almost as long as the engine is allowed to run, never longer", () => {
    expect(engineSeconds).toBeGreaterThan(0);
    expect(ANALYZE_TIMEOUT_MS).toBeLessThan(engineSeconds * 1000);
    expect(ANALYZE_TIMEOUT_MS).toBeGreaterThanOrEqual(engineSeconds * 1000 - 30_000);
  });
});

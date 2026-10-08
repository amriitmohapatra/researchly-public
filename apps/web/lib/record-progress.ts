/**
 * Recording a check for the writer's progress view (S4), from the website:
 * only signed in, only when they switched "Keep my progress" on, and fire
 * and forget. Counts only (lib/progress.ts decides the row); a failure is
 * swallowed here and never reaches the results.
 */
import type { AnalyzeResponse } from "@researchly/contract";
import { recordProgress } from "./progress";

type Recorder = (data: Pick<AnalyzeResponse, "suggestions" | "metrics" | "profile">, keep: boolean) => Promise<unknown>;

export function recordCheck(
  data: Pick<AnalyzeResponse, "suggestions" | "metrics" | "profile">,
  opts: { signedIn: boolean; keep: boolean },
  record: Recorder = recordProgress,
): void {
  if (!opts.signedIn || !opts.keep) return;
  try {
    void record(data, true).catch(() => undefined);
  } catch {
    /* never let progress affect a check */
  }
}

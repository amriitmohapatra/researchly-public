/**
 * Which degraded tiers deserve a banner.
 *
 * CLAUDE.md: no tier may fail silently. But a missing optional tier that the
 * service never claims to run is normal and showing it would be noise:
 * the learned edit tagger (`gec`) ships without a model and is opt-in.
 */
import type { TierHealth } from "@researchly/contract";

const FAULT_STATES = new Set(["error", "unstarted"]);
/**
 * Tiers whose absence silently removes whole classes of suggestions, or (the
 * `files` tier, reported only when degraded) changes how LaTeX and .docx are
 * read.
 */
const CORE_TIERS = new Set(["grammar", "spelling", "parser", "files"]);

export function shouldBanner(t: TierHealth): boolean {
  if (t.ok) return false;
  if (FAULT_STATES.has(t.state)) return true;
  if (CORE_TIERS.has(t.tier)) return true;
  return false; // e.g. gec missing/disabled — expected in this build
}

export interface Banner {
  tier: string;
  title: string;
  detail: string;
  remedy: string;
}

export function healthBanners(health: readonly TierHealth[] | undefined): Banner[] {
  if (!health) return [];
  return health.filter(shouldBanner).map((t) => {
    const label = t.label || t.tier;
    const title =
      t.state === "unstarted"
        ? `${label} checks are still starting`
        : t.tier === "files"
          ? `${label} is limited on this engine`
          : `${label} checks unavailable`;
    return { tier: t.tier, title, detail: t.detail, remedy: t.remedy };
  });
}

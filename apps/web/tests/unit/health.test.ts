import { describe, expect, it } from "vitest";
import type { TierHealth } from "@researchly/contract";
import { healthBanners, shouldBanner } from "@/lib/health";

const t = (tier: string, ok: boolean, state: string, detail = "", remedy = ""): TierHealth => ({
  tier,
  label: tier.charAt(0).toUpperCase() + tier.slice(1),
  ok,
  state,
  detail,
  remedy,
});

describe("health banner logic", () => {
  it("never banners a healthy tier", () => {
    expect(shouldBanner(t("grammar", true, "ready"))).toBe(false);
    expect(shouldBanner(t("grammar", true, "unstarted"))).toBe(false);
  });

  it("banners grammar whenever it is not ok, whatever the state", () => {
    for (const state of ["missing", "disabled", "error", "unstarted"]) {
      expect(shouldBanner(t("grammar", false, state))).toBe(true);
    }
  });

  it("does not banner the learned tier when it is simply missing or opt-in (normal in this build)", () => {
    expect(shouldBanner(t("gec", false, "missing"))).toBe(false);
    expect(shouldBanner(t("gec", false, "disabled"))).toBe(false);
  });

  it("banners any tier that errored or has not started", () => {
    expect(shouldBanner(t("gec", false, "error"))).toBe(true);
    expect(shouldBanner(t("spelling", false, "unstarted"))).toBe(true);
  });

  it("banners a missing core tier (spelling, parser) — no tier fails silently", () => {
    expect(shouldBanner(t("spelling", false, "missing"))).toBe(true);
    expect(shouldBanner(t("parser", false, "missing"))).toBe(true);
  });

  it("banners the files tier: it is only reported when degraded (S2)", () => {
    const files = { ...t("files", false, "missing", "pylatexenc not installed: LaTeX markup is masked by a simpler fallback", "pip install pylatexenc"), label: "File reading" };
    expect(shouldBanner(files)).toBe(true);
    expect(healthBanners([files])[0]!.title).toBe("File reading is limited on this engine");
  });

  it("builds calm titles with the engine's detail and remedy", () => {
    const banners = healthBanners([
      t("parser", true, "ready"),
      t("grammar", false, "error", "LanguageTool failed to start", "retrying shortly"),
      t("gec", false, "missing"),
    ]);
    expect(banners).toEqual([
      { tier: "grammar", title: "Grammar checks unavailable", detail: "LanguageTool failed to start", remedy: "retrying shortly" },
    ]);
  });

  it("words an unstarted tier as starting, not broken", () => {
    expect(healthBanners([t("grammar", false, "unstarted")])[0]!.title).toBe("Grammar checks are still starting");
  });

  it("copes with no health array", () => {
    expect(healthBanners(undefined)).toEqual([]);
  });
});

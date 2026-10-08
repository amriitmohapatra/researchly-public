import type { Page, Request, Route } from "@playwright/test";
import type { AnalyzeRequest } from "@researchly/contract";
import type { RuleInfo } from "@researchly/contract";
import { CHECKLISTS, ENGINE, PROFILES, responseFor, RULES_REGISTRY } from "./fixtures";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, GET, OPTIONS",
  "access-control-allow-headers": "content-type",
  "access-control-expose-headers": "retry-after, x-request-id",
};

export type Handler = (req: AnalyzeRequest, route: Route) => Promise<void> | void;

export async function json(route: Route, status: number, body: unknown, headers: Record<string, string> = {}) {
  await route.fulfill({ status, headers: { ...CORS, ...headers }, contentType: "application/json", body: JSON.stringify(body) });
}

/**
 * Mock /v1/analyze (and /v1/rules, which the page asks once per engine, for
 * the article types' labels and the rules' scopes: `rules` is the registry,
 * or null for an engine without one). Returns the list of request bodies
 * the page sent.
 */
export async function mockEngine(page: Page, handler?: Handler, rules: RuleInfo[] | null = RULES_REGISTRY): Promise<AnalyzeRequest[]> {
  const seen: AnalyzeRequest[] = [];
  await page.route(`${ENGINE}/v1/rules`, async (route) => {
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    if (rules === null) return json(route, 500, { error: { code: "internal", message: "no registry", request_id: "req-rules" } });
    return json(route, 200, { rules, profiles: PROFILES, checklists: CHECKLISTS });
  });
  await page.route(`${ENGINE}/v1/analyze`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const body = route.request().postDataJSON() as AnalyzeRequest;
    seen.push(body);
    if (handler) await handler(body, route);
    else await json(route, 200, responseFor(body));
  });
  return seen;
}

/** Every request the page makes to its own (Next.js) origin. */
export function recordOwnOriginRequests(page: Page, baseURL: string): Request[] {
  const own: Request[] = [];
  page.on("request", (r) => {
    if (r.url().startsWith(baseURL)) own.push(r);
  });
  return own;
}

export async function paste(page: Page, text: string) {
  await page.getByLabel("Text to check").fill(text);
}

export async function check(page: Page) {
  await page.getByTestId("check").click();
}

/** Parse "rgb(r, g, b)" / "rgba(...)" / "color(srgb r g b)". */
export function rgb(css: string): [number, number, number] {
  const m = css.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const [r, g, b] = m[1]!.split(/[ ,/]+/).filter(Boolean).map(Number);
    return [r!, g!, b!];
  }
  const s = css.match(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)/);
  if (s) return [Number(s[1]) * 255, Number(s[2]) * 255, Number(s[3]) * 255];
  throw new Error(`cannot parse colour ${css}`);
}

/** True for colours a reader would call red/red-orange (hue within ±25° of red, saturated). */
export function isReddish([r, g, b]: [number, number, number]): boolean {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max - min < 40) return false; // greyish
  let h = 0;
  if (max === r) h = ((g - b) / (max - min)) * 60;
  else if (max === g) h = (2 + (b - r) / (max - min)) * 60;
  else h = (4 + (r - g) / (max - min)) * 60;
  if (h < 0) h += 360;
  return h <= 25 || h >= 335;
}

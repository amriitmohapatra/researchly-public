import { defineConfig, devices } from "@playwright/test";
import { SUPABASE_KEY, SUPABASE_URL } from "./e2e/supabase-mock";

/**
 * E2E runs against production builds (`next build && next start`). The
 * engine is mocked with page.route at ENGINE; the build bakes that origin
 * into the page and its CSP, so the CSP's connect-src is exercised too.
 *
 * Two builds, two projects:
 * - "chromium": the S1 site, built with NO Supabase config. The S1 suite runs
 *   here unchanged, proving accounts stay out of the way when unset.
 * - "accounts": the same code built with a (mocked) Supabase project, for the
 *   S2 specs (e2e/accounts*.spec.ts). Supabase is mocked with page.route too.
 * Each build gets its own output directory (RESEARCHLY_DIST_DIR) so they can
 * coexist.
 */
const PORT = Number(process.env.E2E_PORT ?? 3100);
const ACCOUNTS_PORT = PORT + 1;
const ENGINE = "http://127.0.0.1:8099";
const env = { NEXT_PUBLIC_ENGINE_URL: ENGINE, NEXT_TELEMETRY_DISABLED: "1" };
const ACCOUNTS_SPECS = /(^|[\\/])accounts[^\\/]*\.spec\.ts$/;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0, // a flaky test is a bug to root-cause, never a retry to hide
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 900 },
  },
  projects: [
    { name: "chromium", testIgnore: ACCOUNTS_SPECS, use: { baseURL: `http://localhost:${PORT}` } },
    { name: "accounts", testMatch: ACCOUNTS_SPECS, use: { baseURL: `http://localhost:${ACCOUNTS_PORT}` } },
  ],
  webServer: [
    {
      command: `npx next build && npx next start --port ${PORT}`,
      url: `http://localhost:${PORT}`,
      timeout: 240_000,
      reuseExistingServer: false, // always test a fresh build of the current code
      env: { ...env, RESEARCHLY_DIST_DIR: ".next" },
    },
    {
      command: `npx next build && npx next start --port ${ACCOUNTS_PORT}`,
      url: `http://localhost:${ACCOUNTS_PORT}`,
      timeout: 240_000,
      reuseExistingServer: false,
      env: {
        ...env,
        RESEARCHLY_DIST_DIR: ".next-accounts",
        NEXT_PUBLIC_SUPABASE_URL: SUPABASE_URL,
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: SUPABASE_KEY,
      },
    },
  ],
});

/**
 * The one place supabase-js is loaded (scripts/check-boundary.mjs enforces it).
 *
 * - Browser only: `client-only` makes importing this from server code a build
 *   error, and the library itself is loaded with a dynamic import() on first
 *   use, so it is not even in the server render or in a build without
 *   accounts (S1 behaviour, no Supabase code path).
 * - PKCE: the email link's one-time code is exchanged for a session here, in
 *   the browser (detectSessionInUrl). Next.js server code never sees a token.
 * - The session lives in localStorage under `sb-<project-ref>-auth-token`, by
 *   supabase-js design. It is the only thing this app stores besides the
 *   format preference; document text is never stored.
 */
import "client-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { SUPABASE } from "./config";

let client: Promise<SupabaseClient> | null = null;

/** The shared client, or null in a build without accounts (or on the server). */
export function getSupabase(): Promise<SupabaseClient> | null {
  const cfg = SUPABASE;
  if (!cfg || typeof window === "undefined") return null;
  client ??= import("@supabase/supabase-js").then(({ createClient }) =>
    createClient(cfg.url, cfg.key, {
      auth: {
        flowType: "pkce",
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: true,
      },
    }),
  );
  return client;
}

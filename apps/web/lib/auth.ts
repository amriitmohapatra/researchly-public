/**
 * Who is signed in, as a tiny external store over supabase-js (S2).
 *
 * - Email magic link, PKCE: the code in the link is exchanged in this browser
 *   by supabase-js (lib/supabase.ts). Next.js server code never sees it.
 * - Components read the state with useAuth(); nothing here is persisted by
 *   this app (supabase-js keeps its own session in localStorage).
 * - The access token is never put in React state: engine calls fetch it at
 *   call time through `engineAuth`.
 * - In a build without accounts the state is always { status: "off" } and
 *   supabase-js is never loaded.
 */
import "client-only";
import { useSyncExternalStore } from "react";
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { ACCOUNTS_ENABLED } from "./config";
import type { EngineAuth } from "./engine";
import { signInErrorMessage, signInLinkErrorMessage, verifyCodeErrorMessage, type AuthErrorLike } from "./errors";
import { getSupabase } from "./supabase";

export type AuthState =
  | { status: "off" }
  | { status: "loading" }
  | { status: "signed_out" }
  | { status: "signed_in"; email: string };

export interface AuthSnapshot {
  auth: AuthState;
  /** Shown in the sign-in dialog: why it opened (e.g. "Checking a file needs an account."). */
  dialogReason: string | null;
  dialogOpen: boolean;
  /** A one-off message about the sign-in itself (an expired link, a forced sign-out). */
  notice: string | null;
}

const SERVER_SNAPSHOT: AuthSnapshot = Object.freeze<AuthSnapshot>({
  auth: ACCOUNTS_ENABLED ? { status: "loading" } : { status: "off" },
  dialogReason: null,
  dialogOpen: false,
  notice: null,
});

let snapshot: AuthSnapshot = SERVER_SNAPSHOT;
const listeners = new Set<() => void>();
let started = false;

function set(patch: Partial<AuthSnapshot>) {
  snapshot = { ...snapshot, ...patch };
  for (const l of listeners) l();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  void start();
  return () => listeners.delete(onChange);
}

export function useAuth(): AuthSnapshot {
  return useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => SERVER_SNAPSHOT,
  );
}

function stateFrom(session: Session | null): AuthState {
  return session?.user ? { status: "signed_in", email: session.user.email ?? "your account" } : { status: "signed_out" };
}

const URL_ERROR_KEYS = ["error", "error_code", "error_description"];

/** An error the email link brought back (Supabase puts it in the hash or the query). */
function urlError(): string | undefined | null {
  const url = new URL(window.location.href);
  const hash = new URLSearchParams(url.hash.replace(/^#/, ""));
  const has = (k: string) => url.searchParams.has(k) || hash.has(k);
  if (!URL_ERROR_KEYS.some(has)) return null;
  return url.searchParams.get("error_code") ?? hash.get("error_code") ?? undefined;
}

/** Remove sign-in leftovers (error details, an unusable code) from the address bar. */
function cleanUrl(alsoCode: boolean) {
  const url = new URL(window.location.href);
  const hash = new URLSearchParams(url.hash.replace(/^#/, ""));
  for (const k of [...URL_ERROR_KEYS, ...(alsoCode ? ["code", "sb_flow_id"] : [])]) {
    url.searchParams.delete(k);
    hash.delete(k);
  }
  url.hash = hash.toString();
  window.history.replaceState(window.history.state, "", url.toString());
}

async function start() {
  if (started || !ACCOUNTS_ENABLED) return;
  started = true;
  const pending = getSupabase();
  if (!pending) return;
  let sb: SupabaseClient;
  try {
    sb = await pending;
  } catch {
    set({ auth: { status: "signed_out" }, notice: "The sign-in service could not be loaded. Reload the page to try again." });
    return;
  }
  const linkError = urlError();
  const hadCode = new URL(window.location.href).searchParams.has("code");
  sb.auth.onAuthStateChange((_event, session) => {
    // Only state here: calling back into supabase-js from this callback can deadlock.
    set({ auth: stateFrom(session) });
  });
  const { error } = await sb.auth.initialize();
  const { data } = await sb.auth.getSession();
  set({ auth: stateFrom(data.session) });

  if (linkError !== null || error) {
    const code = linkError ?? (error as AuthErrorLike & { details?: { code?: string } })?.details?.code ?? (error as AuthErrorLike)?.code;
    cleanUrl(true);
    if (!data.session) openSignIn(null, signInLinkErrorMessage(code));
  } else if (hadCode && !data.session) {
    // A link opened in another browser than the one that asked for it: the
    // PKCE verifier is not here, so the code can't be used.
    cleanUrl(true);
    openSignIn(
      null,
      "That sign-in link was opened in a different browser from the one where you asked for it. Ask for a new link here, or open the link in the other browser.",
    );
  }
}

/** Open the sign-in dialog. `reason` explains why (shown above the email field). */
export function openSignIn(reason: string | null = null, notice: string | null = null) {
  if (!ACCOUNTS_ENABLED) return;
  set({ dialogOpen: true, dialogReason: reason, notice });
}

export function closeSignIn() {
  set({ dialogOpen: false, dialogReason: null, notice: null });
}

export type SignInResult = { ok: true } | { ok: false; message: string };

/** Ask Supabase to email a magic link that returns to this site. */
export async function sendMagicLink(email: string): Promise<SignInResult> {
  const pending = getSupabase();
  if (!pending) return { ok: false, message: "Sign-in is not available on this site." };
  try {
    const sb = await pending;
    const { error } = await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    return error ? { ok: false, message: signInErrorMessage(error) } : { ok: true };
  } catch {
    return { ok: false, message: signInErrorMessage({ status: 0 }) };
  }
}

/* ---------- sign-in by emailed code (the Word add-in, S3) ---------- */

/** Supabase's email one-time codes are 6 digits by default, and can be set up to 10. */
export const EMAIL_CODE = /^[0-9]{6,10}$/;

/** "123 456" or "123-456" as typed or pasted: digits only. */
export function normaliseCode(raw: string): string {
  return raw.replace(/[\s-]/g, "");
}

/**
 * Email a one-time code (S3). Used inside the Word taskpane, where a link
 * would open in the system browser rather than back in Word. The same email
 * also carries the usual link, which signs the writer in on the website.
 */
export async function sendEmailCode(email: string): Promise<SignInResult> {
  const pending = getSupabase();
  if (!pending) return { ok: false, message: "Sign-in is not available here." };
  try {
    const sb = await pending;
    const { error } = await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    return error ? { ok: false, message: signInErrorMessage(error).replace("sign-in link", "sign-in code") } : { ok: true };
  } catch {
    return { ok: false, message: signInErrorMessage({ status: 0 }) };
  }
}

/** Exchange the emailed code for a session, kept by supabase-js in this taskpane's own storage. */
export async function verifyEmailCode(email: string, rawCode: string): Promise<SignInResult> {
  const code = normaliseCode(rawCode);
  if (!EMAIL_CODE.test(code)) return { ok: false, message: "Enter the code from the email: 6 to 10 digits." };
  const pending = getSupabase();
  if (!pending) return { ok: false, message: "Sign-in is not available here." };
  try {
    const sb = await pending;
    const { data, error } = await sb.auth.verifyOtp({ email, token: code, type: "email" });
    if (error || !data.session) return { ok: false, message: verifyCodeErrorMessage(error ?? {}) };
    set({ auth: stateFrom(data.session) });
    return { ok: true };
  } catch {
    return { ok: false, message: verifyCodeErrorMessage({ status: 0 }) };
  }
}

/** Sign out of this browser (the session is revoked; other devices stay signed in). */
export async function signOut(): Promise<void> {
  const pending = getSupabase();
  if (!pending) return;
  try {
    const sb = await pending;
    await sb.auth.signOut({ scope: "local" });
  } catch {
    // Offline: supabase-js has still forgotten the session in this browser.
  }
  set({ auth: { status: "signed_out" } });
}

function isTransient(err: AuthErrorLike): boolean {
  return err.name === "AuthRetryableFetchError" || err.status === 0 || (err.status ?? 0) >= 500;
}

/** The token source for engine calls; null in a build without accounts. */
export function getEngineAuth(): EngineAuth | null {
  const pending = getSupabase();
  if (!pending) return null;
  return {
    async token() {
      const sb = await pending;
      const { data } = await sb.auth.getSession();
      return data.session?.access_token ?? null;
    },
    async refresh() {
      const sb = await pending;
      const { data, error } = await sb.auth.refreshSession();
      if (error) return { token: null, transient: isTransient(error) };
      return { token: data.session?.access_token ?? null, transient: false };
    },
    async signOutLocally() {
      const sb = await pending;
      await sb.auth.signOut({ scope: "local" });
      set({ auth: { status: "signed_out" } });
    },
  };
}

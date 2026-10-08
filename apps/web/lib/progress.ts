/**
 * The personal progress view's data (S4): opt-in, counts only.
 *
 * When a signed-in writer has switched "Keep my progress" on, each check
 * records how many times each rule fired, the number of words and the
 * article type. Never text, never a file name. The database refuses a row
 * from a writer who has not opted in (supabase/migrations/
 * 20261008140000_s4_progress.sql), so a bug here cannot start recording.
 */
import "client-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { AnalyzeResponse, DocumentType } from "@researchly/contract";
import { accountErrorMessage, type AccountResult } from "./account";
import { getSupabase } from "./supabase";

/** One recorded check, as the progress page reads it. */
export interface ProgressEvent {
  created_at: string;
  words: number;
  document_type: DocumentType;
  counts: Record<string, number>;
}

const RULE_ID = /^[A-Z]{1,4}[0-9]{2,4}$/;

/** The row a check would record: rule counts, words, article type. Pure, unit-tested. */
export function progressRow(data: Pick<AnalyzeResponse, "suggestions" | "metrics" | "profile">): {
  words: number;
  document_type: DocumentType;
  counts: Record<string, number>;
} {
  const counts: Record<string, number> = {};
  for (const s of data.suggestions) {
    if (RULE_ID.test(s.rule_id)) counts[s.rule_id] = (counts[s.rule_id] ?? 0) + 1;
  }
  return {
    words: Math.max(0, Math.min(2_000_000, Math.round(data.metrics?.words ?? 0))),
    document_type: data.profile?.id ?? "auto",
    counts,
  };
}

async function run<T>(fn: (sb: SupabaseClient) => Promise<AccountResult<T>>): Promise<AccountResult<T>> {
  try {
    const sb = await getSupabase();
    if (!sb) return { ok: false, message: "Accounts are not available on this site." };
    return await fn(sb);
  } catch {
    return { ok: false, message: "Could not reach your account. Check your connection and try again." };
  }
}

/** Whether the writer has opted in; false when there is no settings row or the column is missing (migration not run). */
export function loadKeepProgress(): Promise<AccountResult<boolean>> {
  return run(async (sb) => {
    const { data, error } = await sb.from("user_settings").select("keep_progress").maybeSingle();
    if (error) return { ok: false, message: accountErrorMessage(error) };
    return { ok: true, data: (data as { keep_progress?: unknown } | null)?.keep_progress === true };
  });
}

export function saveKeepProgress(on: boolean): Promise<AccountResult<null>> {
  return run(async (sb) => {
    const { error } = await sb.from("user_settings").upsert({ keep_progress: on }, { onConflict: "user_id" });
    return error ? { ok: false, message: accountErrorMessage(error) } : { ok: true, data: null };
  });
}

/**
 * Record one check, only when `keep` is true (the caller's loaded opt-in).
 * Fire-and-forget from the surfaces: a failure never affects the check.
 */
export async function recordProgress(
  data: Pick<AnalyzeResponse, "suggestions" | "metrics" | "profile">,
  keep: boolean,
): Promise<AccountResult<null>> {
  if (!keep) return { ok: true, data: null };
  return run(async (sb) => {
    const { error } = await sb.from("progress_events").insert(progressRow(data));
    return error ? { ok: false, message: accountErrorMessage(error) } : { ok: true, data: null };
  });
}

/** The newest checks first, at most `limit` (the table keeps 1,000). */
export function loadProgress(limit = 200): Promise<AccountResult<ProgressEvent[]>> {
  return run(async (sb) => {
    const { data, error } = await sb
      .from("progress_events")
      .select("created_at, words, document_type, counts")
      .order("created_at", { ascending: false })
      .limit(limit);
    if (error) return { ok: false, message: accountErrorMessage(error) };
    return { ok: true, data: (data ?? []) as ProgressEvent[] };
  });
}

/** Delete every recorded check of this writer (RLS scopes it; filtered by their id too). */
export function deleteProgress(): Promise<AccountResult<null>> {
  return run(async (sb) => {
    const { data } = await sb.auth.getSession();
    const uid = data.session?.user.id;
    if (!uid) return { ok: false, message: "Sign in again to delete your progress; nothing was changed." };
    const { error } = await sb.from("progress_events").delete().eq("user_id", uid);
    return error ? { ok: false, message: accountErrorMessage(error) } : { ok: true, data: null };
  });
}

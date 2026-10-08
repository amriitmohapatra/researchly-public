/**
 * Turning a failed check into something a writer can act on.
 *
 * Contract: every non-2xx body is an ErrorResponse whose `message` never
 * contains document text, so it is safe to show. `request_id` is shown for
 * server faults so a user can quote it when reporting a problem.
 * Whatever happens, the user's text stays in the editor.
 */
import { MAX_CONTENT_CHARS, MAX_UPLOAD_BYTES, type ErrorResponse } from "@researchly/contract";

export type CheckErrorKind =
  | "unreachable"
  | "timeout"
  | "too_large"
  | "rate_limited"
  | "invalid"
  | "server"
  | "bad_response"
  // S2: accounts and files
  | "sign_in_required"
  | "unauthorized"
  | "signed_out"
  | "auth_unavailable"
  | "unsupported_file"
  | "unreadable_file";

export interface CheckError {
  kind: CheckErrorKind;
  title: string;
  message: string;
  /** The engine's machine-readable error code, when it sent one. */
  code?: string;
  /** Present when the engine returned one; shown so the user can report it. */
  requestId?: string;
  /** Whether a plain Retry is a sensible next step. */
  retryable: boolean;
  /** Whether signing in is the way forward (the UI offers a Sign in button). */
  signIn?: boolean;
}

/** What was sent: pasted text (/v1/analyze) or a file (/v1/analyze-file). Changes some wording. */
export interface ErrorContext {
  upload?: boolean;
}

type Headers = { get(name: string): string | null };

export function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== "object" || body === null) return false;
  const err = (body as { error?: unknown }).error;
  if (typeof err !== "object" || err === null) return false;
  const e = err as Record<string, unknown>;
  return typeof e.code === "string" && typeof e.message === "string" && typeof e.request_id === "string";
}

const fmt = new Intl.NumberFormat("en-GB");

/** Map an HTTP failure from the engine to a user-facing error. */
export function errorFromResponse(
  status: number,
  body: unknown,
  headers?: Headers,
  context: ErrorContext = {},
): CheckError {
  const parsed = isErrorResponse(body) ? body.error : undefined;
  const requestId = parsed?.request_id || headers?.get("x-request-id") || undefined;
  const e = mapError(status, parsed, requestId, headers, context);
  return parsed?.code ? { ...e, code: parsed.code } : e;
}

function mapError(
  status: number,
  parsed: ErrorResponse["error"] | undefined,
  requestId: string | undefined,
  headers: Headers | undefined,
  context: ErrorContext,
): CheckError {
  const code = parsed?.code;

  // Accounts (S2). Decided by code first: a 503 auth_unavailable is not a server fault.
  if (status === 401 && code === "sign_in_required") {
    return {
      kind: "sign_in_required",
      title: context.upload ? "Sign in to check a file" : "Sign in to check this much text",
      message: parsed?.message || "This needs an account. Sign in with your email address; your text is still here.",
      requestId,
      retryable: false,
      signIn: true,
    };
  }
  if (status === 401) {
    return {
      kind: "unauthorized",
      title: "Your sign-in has expired",
      message: parsed?.message || "Sign in again to continue. Your text is still here.",
      requestId,
      retryable: false,
      signIn: true,
    };
  }
  if (code === "auth_unavailable") {
    return {
      kind: "auth_unavailable",
      title: "Your sign-in could not be checked just now",
      message:
        "The engine could not confirm your sign-in, so nothing was checked and nothing was stored. Try again in a moment; your text is still here.",
      requestId,
      retryable: true,
    };
  }
  if (code === "unsupported_file" || (context.upload && status === 415)) {
    return {
      kind: "unsupported_file",
      title: "This file type can't be checked",
      message: parsed?.message || `Researchly reads ${UPLOAD_TYPES_SENTENCE}`,
      requestId,
      retryable: false,
    };
  }
  if (code === "unreadable_file") {
    return {
      kind: "unreadable_file",
      title: "This file could not be read",
      message: parsed?.message || "Save it again from Word or Overleaf, then upload the new copy.",
      requestId,
      retryable: false,
    };
  }
  if (status === 413 && context.upload) {
    return {
      kind: "too_large",
      title: "This file is too large to check",
      message:
        parsed?.message ||
        `Files up to ${formatBytes(MAX_UPLOAD_BYTES)} can be checked. Try checking one chapter at a time.`,
      requestId,
      retryable: false,
    };
  }

  if (status === 413) {
    return {
      kind: "too_large",
      title: "This text is too long for one check",
      message: `The engine accepts up to ${fmt.format(MAX_CONTENT_CHARS)} characters at a time. Try checking one chapter or section at a time.`,
      requestId,
      retryable: false,
    };
  }
  if (status === 429) {
    const wait = retryAfterSeconds(headers?.get("retry-after") ?? null);
    return {
      kind: "rate_limited",
      title: "Too many checks in a short time",
      message:
        wait !== null
          ? `Please wait about ${wait} second${wait === 1 ? "" : "s"}, then try again. Your text is still here.`
          : "Please wait a moment, then try again. Your text is still here.",
      requestId,
      retryable: true,
    };
  }
  if (status === 400 || status === 422) {
    return {
      kind: "invalid",
      title: "The engine could not read this request",
      message: parsed?.message
        ? `${parsed.message}`
        : "Something about the request was not accepted. Check the format setting and try again.",
      requestId,
      retryable: false,
    };
  }
  if (status >= 500) {
    return {
      kind: "server",
      title: "Something went wrong on our side",
      message:
        "The check did not complete. Your text was not stored. If this keeps happening, please report it and quote the reference below.",
      requestId,
      retryable: true,
    };
  }
  return {
    kind: "bad_response",
    title: "Unexpected response from the engine",
    message: `The engine answered with status ${status}. Your text is still here; try again shortly.`,
    requestId,
    retryable: true,
  };
}

/** After a 401, a refresh and one retry that still failed: this browser has been signed out. */
export function signedOutError(): CheckError {
  return {
    kind: "signed_out",
    title: "You have been signed out",
    message:
      "Your sign-in could not be renewed, so this browser has been signed out. Sign in again to check with your settings. Your text is still here.",
    retryable: false,
    signIn: true,
  };
}

/** The session could not be renewed for a passing reason (offline, Supabase busy): nothing is signed out. */
export function refreshUnavailableError(): CheckError {
  return {
    kind: "auth_unavailable",
    title: "Your sign-in could not be renewed just now",
    message: "Nothing was checked or stored. Check your connection and try again; your text is still here.",
    retryable: true,
  };
}

/** The engine's host for the "unreachable" message, or "" if the URL won't parse. */
function engineHost(engineUrl: string): string {
  try {
    return new URL(engineUrl).host;
  } catch {
    return "";
  }
}

/**
 * `engineUrl` is named in the "unreachable" message: when a deployment is
 * built against the wrong engine address, the fetch fails identically to a
 * dropped connection, and the host is the one clue that tells them apart.
 * It is public (the page's security policy already lists it).
 */
export function networkError(timedOut: boolean, engineUrl = ""): CheckError {
  const host = engineHost(engineUrl);
  return timedOut
    ? {
        kind: "timeout",
        title: "The check took too long",
        message: "The engine did not answer in time. Your text is still here. Try again, or check a shorter part.",
        retryable: true,
      }
    : {
        kind: "unreachable",
        title: "Could not reach the checking engine",
        message:
          "Your text is still here and nothing was sent anywhere else. Check your connection and try again." +
          (host ? ` If it keeps failing, the site may be set up with the wrong engine address (tried ${host}).` : ""),
        retryable: true,
      };
}

/** Something in the page failed before the request was sent (e.g. the sign-in library would not load). */
export function clientError(): CheckError {
  return {
    kind: "unreachable",
    title: "The check could not be sent",
    message: "Something in this page failed before anything was sent; nothing was stored. Reload the page and try again. Your text is still here.",
    retryable: true,
  };
}

export function badPayloadError(detail: string): CheckError {
  return {
    kind: "bad_response",
    title: "Unexpected response from the engine",
    message: `${detail} Reloading the page usually fixes this; your text is still here.`,
    retryable: true,
  };
}

/** Parses a Retry-After header (seconds or HTTP date). Returns whole seconds, or null. */
export function retryAfterSeconds(value: string | null, now: number = Date.now()): number | null {
  if (!value) return null;
  const v = value.trim();
  if (/^\d+$/.test(v)) return Math.max(0, Math.min(3600, Number(v)));
  const t = Date.parse(v);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.min(3600, Math.ceil((t - now) / 1000)));
}

/** The file types the engine reads, as the engine's own message lists them. */
export const UPLOAD_TYPES_SENTENCE = ".docx, .tex, Overleaf .zip, .md, .qmd, .Rmd and .txt files.";

const bytesFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

/** 26214400 → "25 MB" (binary megabytes, as the engine's cap is 25 MiB). */
export function formatBytes(n: number): string {
  if (n >= 1024 * 1024) return `${bytesFmt.format(n / (1024 * 1024))} MB`;
  if (n >= 1024) return `${bytesFmt.format(n / 1024)} KB`;
  return `${n} bytes`;
}

/* ---------- sign-in (Supabase) ---------- */

/** The parts of a supabase-js AuthError this app looks at. */
export interface AuthErrorLike {
  name?: string;
  status?: number;
  code?: string;
}

/**
 * A Supabase sign-in failure, in words a writer can act on. Supabase's own
 * text is not shown: it is written for developers.
 */
/**
 * True only when the request never got an answer. supabase-js also raises
 * AuthRetryableFetchError for 5xx replies (500 included), and Supabase
 * answers 500 when it cannot send the email (e.g. custom SMTP refused the
 * login): blaming the writer's connection then sent them the wrong way.
 */
function unreachable(err: AuthErrorLike): boolean {
  const status = err.status ?? 0;
  return status === 0 && (err.name === "AuthRetryableFetchError" || err.status === 0);
}

export function signInErrorMessage(err: AuthErrorLike): string {
  const code = err.code ?? "";
  if (unreachable(err)) {
    return "Could not reach the sign-in service. Check your connection and try again.";
  }
  if (err.status === 429 || code.startsWith("over_")) {
    return "Too many sign-in emails were asked for in a short time. Look in your inbox (and spam folder) for the last one, or wait a few minutes and try again.";
  }
  if (code === "email_address_invalid" || code === "validation_failed") {
    return "That does not look like a valid email address. Check it and try again.";
  }
  if (
    code === "signup_disabled" ||
    code === "otp_disabled" ||
    code === "email_provider_disabled" ||
    code === "email_address_not_authorized" ||
    code === "user_banned"
  ) {
    return "A sign-in link can't be sent to this address. Check that it is typed correctly.";
  }
  if ((err.status ?? 0) >= 500) {
    return "The sign-in service could not send the email. Try again in a few minutes; if it keeps happening, use Report a problem.";
  }
  return "The sign-in link could not be sent. Try again in a moment.";
}

/**
 * The email link came back with an error (in the URL), or its one-time code
 * could not be exchanged. Expired and reused links are by far the commonest.
 */
export function signInLinkErrorMessage(code: string | undefined): string {
  switch (code) {
    case "otp_expired":
    case "flow_state_expired":
    case "flow_state_not_found":
    case "bad_code_verifier":
      return "That sign-in link has expired or has already been used. Ask for a new one.";
    default:
      return "That sign-in link could not be used. Ask for a new one.";
  }
}

/** The emailed one-time code (the Word add-in, S3) could not be used. */
export function verifyCodeErrorMessage(err: AuthErrorLike): string {
  const code = err.code ?? "";
  if (unreachable(err)) {
    return "Could not reach the sign-in service. Check your connection and try again.";
  }
  if (err.status === 429 || code.startsWith("over_")) {
    return "Too many tries in a short time. Wait a few minutes, then ask for a new code.";
  }
  if (code === "otp_expired") {
    return "That code has expired or has already been used. Ask for a new one.";
  }
  if ((err.status ?? 0) >= 500) {
    return "The sign-in service had a problem. Try again in a few minutes.";
  }
  return "That code is not right. Check the latest email and try again, or ask for a new code.";
}

import { describe, expect, it } from "vitest";
import {
  errorFromResponse,
  formatBytes,
  isErrorResponse,
  networkError,
  retryAfterSeconds,
  signedOutError,
  signInErrorMessage,
  signInLinkErrorMessage,
} from "@/lib/errors";

const body = (code: string, message = "msg", request_id = "req-123") => ({ error: { code, message, request_id } });
const headers = (h: Record<string, string>) => ({ get: (k: string) => h[k.toLowerCase()] ?? null });

describe("error mapping", () => {
  it("recognises the contract's ErrorResponse shape", () => {
    expect(isErrorResponse(body("internal"))).toBe(true);
    expect(isErrorResponse({ error: { code: "x", message: "y" } })).toBe(false);
    expect(isErrorResponse({ detail: [] })).toBe(false);
    expect(isErrorResponse(null)).toBe(false);
  });

  it("413 explains the limit and is not retryable", () => {
    const e = errorFromResponse(413, body("payload_too_large"));
    expect(e.kind).toBe("too_large");
    expect(e.message).toContain("1,000,000");
    expect(e.retryable).toBe(false);
  });

  it("429 asks the user to slow down, using Retry-After when present", () => {
    const e = errorFromResponse(429, body("rate_limited"), headers({ "retry-after": "12" }));
    expect(e.kind).toBe("rate_limited");
    expect(e.message).toContain("12 seconds");
    expect(e.retryable).toBe(true);
    expect(errorFromResponse(429, null).message).toMatch(/wait a moment/);
  });

  it("400 and 422 show the engine's (text-free) message", () => {
    expect(errorFromResponse(422, body("invalid_request", "format must be one of plain, markdown, latex")).message).toBe(
      "format must be one of plain, markdown, latex",
    );
    expect(errorFromResponse(400, null).kind).toBe("invalid");
  });

  it("500 carries the request id so the user can report it", () => {
    const e = errorFromResponse(500, body("internal", "boom", "req-abc"));
    expect(e.kind).toBe("server");
    expect(e.requestId).toBe("req-abc");
    expect(e.retryable).toBe(true);
  });

  it("takes the request id from a header when the body has none", () => {
    expect(errorFromResponse(503, "<html>", headers({ "x-request-id": "hdr-1" })).requestId).toBe("hdr-1");
  });

  it("maps other statuses to an unexpected-response error", () => {
    expect(errorFromResponse(404, null).kind).toBe("bad_response");
  });

  it("network failures keep the user's text and offer retry", () => {
    const e = networkError(false);
    expect(e.kind).toBe("unreachable");
    expect(e.message).toMatch(/still here/);
    expect(e.retryable).toBe(true);
    expect(networkError(true).kind).toBe("timeout");
  });

  it("an unreachable engine is named by host, so a wrong deploy-time address is diagnosable", () => {
    // Regression: the first live deploy was built against a stale engine URL
    // and the page gave no clue which address it had tried.
    const e = networkError(false, "https://researchly-engine-1.asia-southeast1.run.app");
    expect(e.message).toContain("tried researchly-engine-1.asia-southeast1.run.app");
    expect(networkError(false, "not a url").message).not.toMatch(/tried/);
    expect(networkError(false).message).not.toMatch(/tried/);
  });

  it("never echoes document text: messages come only from the engine's message field or fixed copy", () => {
    const secret = "CANARY-7f3a my unpublished finding";
    const e = errorFromResponse(500, { error: { code: "internal", message: "Engine error", request_id: "r" }, content: secret });
    expect(JSON.stringify(e)).not.toContain("CANARY");
  });
});

describe("retryAfterSeconds", () => {
  it("parses delta-seconds", () => {
    expect(retryAfterSeconds("30")).toBe(30);
    expect(retryAfterSeconds(" 5 ")).toBe(5);
  });
  it("parses an HTTP date", () => {
    const now = Date.parse("2026-10-03T10:00:00Z");
    expect(retryAfterSeconds("Sat, 03 Oct 2026 10:00:20 GMT", now)).toBe(20);
  });
  it("caps absurd values and rejects garbage", () => {
    expect(retryAfterSeconds("999999")).toBe(3600);
    expect(retryAfterSeconds("soon")).toBeNull();
    expect(retryAfterSeconds(null)).toBeNull();
  });
});

describe("S2: account and file errors", () => {
  it("401 sign_in_required asks to sign in, with the engine's (text-free) message", () => {
    const e = errorFromResponse(401, body("sign_in_required", "Without an account Researchly checks up to 1,500 words at a time."));
    expect(e.kind).toBe("sign_in_required");
    expect(e.code).toBe("sign_in_required");
    expect(e.signIn).toBe(true);
    expect(e.retryable).toBe(false);
    expect(e.message).toContain("1,500 words");
    expect(errorFromResponse(401, body("sign_in_required", "x"), undefined, { upload: true }).title).toBe("Sign in to check a file");
  });

  it("401 unauthorized is an expired sign-in (the engine client refreshes before showing it)", () => {
    const e = errorFromResponse(401, body("unauthorized", "Your sign-in has expired or is not valid."));
    expect(e.kind).toBe("unauthorized");
    expect(e.code).toBe("unauthorized");
    expect(e.signIn).toBe(true);
    const gone = signedOutError();
    expect(gone.kind).toBe("signed_out");
    expect(gone.message).toMatch(/still here/);
  });

  it("503 auth_unavailable is retryable and not a server fault", () => {
    const e = errorFromResponse(503, body("auth_unavailable", "x", "req-9"));
    expect(e.kind).toBe("auth_unavailable");
    expect(e.retryable).toBe(true);
    expect(e.requestId).toBe("req-9");
    expect(errorFromResponse(503, body("internal")).kind).toBe("server");
  });

  it("415 unsupported_file and 422 unreadable_file show the engine's message", () => {
    const u = errorFromResponse(415, body("unsupported_file", "Researchly reads .docx, .tex, Overleaf .zip, .md, .qmd, .Rmd or .txt files."), undefined, { upload: true });
    expect(u.kind).toBe("unsupported_file");
    expect(u.message).toContain(".Rmd");
    expect(u.retryable).toBe(false);
    const r = errorFromResponse(422, body("unreadable_file", "chapter.md is not UTF-8 text. Save it as UTF-8 and upload it again."));
    expect(r.kind).toBe("unreadable_file");
    expect(r.message).toContain("UTF-8");
    // A plain 422 validation error is still "invalid".
    expect(errorFromResponse(422, body("invalid_request", "x")).kind).toBe("invalid");
  });

  it("413 on an upload talks about the file, not pasted characters", () => {
    const e = errorFromResponse(413, body("payload_too_large", "The file is larger than 25 MB."), undefined, { upload: true });
    expect(e.title).toBe("This file is too large to check");
    expect(e.message).toBe("The file is larger than 25 MB.");
    expect(errorFromResponse(413, null, undefined, { upload: true }).message).toContain("25 MB");
    expect(errorFromResponse(413, body("payload_too_large")).message).toContain("1,000,000 characters");
  });

  it("formats sizes in binary megabytes", () => {
    expect(formatBytes(25 * 1024 * 1024)).toBe("25 MB");
    expect(formatBytes(30_000_000)).toBe("28.6 MB");
    expect(formatBytes(2048)).toBe("2 KB");
  });
});

describe("sign-in messages", () => {
  it("maps Supabase's error codes to plain sentences", () => {
    expect(signInErrorMessage({ status: 429, code: "over_email_send_rate_limit" })).toMatch(/Too many sign-in emails/);
    expect(signInErrorMessage({ status: 400, code: "email_address_invalid" })).toMatch(/valid email address/);
    expect(signInErrorMessage({ status: 422, code: "otp_disabled" })).toMatch(/can't be sent to this address/);
    expect(signInErrorMessage({ status: 400, code: "email_address_not_authorized" })).toMatch(/can't be sent/);
    expect(signInErrorMessage({ name: "AuthRetryableFetchError", status: 0 })).toMatch(/connection/);
    expect(signInErrorMessage({ status: 500 })).toMatch(/could not send the email/);
    // supabase-js wraps 5xx replies as retryable fetch errors too: Supabase
    // answered, so it is not the writer's connection (SMTP refused, say).
    expect(signInErrorMessage({ name: "AuthRetryableFetchError", status: 500 })).toMatch(/could not send the email/);
    expect(signInErrorMessage({ name: "AuthRetryableFetchError", status: 504 })).not.toMatch(/connection/);
    expect(signInErrorMessage({})).toMatch(/could not be sent/);
  });
  it("explains expired or reused links", () => {
    expect(signInLinkErrorMessage("otp_expired")).toMatch(/expired or has already been used/);
    expect(signInLinkErrorMessage("flow_state_not_found")).toMatch(/expired/);
    expect(signInLinkErrorMessage(undefined)).toMatch(/could not be used/);
  });
});

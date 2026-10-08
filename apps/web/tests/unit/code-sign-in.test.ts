import { describe, expect, it } from "vitest";
import { EMAIL_CODE, normaliseCode, verifyEmailCode } from "@/lib/auth";
import { verifyCodeErrorMessage } from "@/lib/errors";

describe("sign-in by emailed code (Word taskpane)", () => {
  it("accepts 6 to 10 digits, as typed or pasted with spaces or a dash", () => {
    for (const c of ["123456", "1234567890", "12345678"]) expect(EMAIL_CODE.test(c)).toBe(true);
    for (const c of ["12345", "12345678901", "12a456", ""]) expect(EMAIL_CODE.test(c)).toBe(false);
    expect(normaliseCode(" 123 456 ")).toBe("123456");
    expect(normaliseCode("1234-5678")).toBe("12345678");
  });

  it("refuses a malformed code before anything is sent", async () => {
    expect(await verifyEmailCode("a@b.co", "12 34")).toEqual({ ok: false, message: "Enter the code from the email: 6 to 10 digits." });
  });

  it("explains failures in words, never Supabase's own text", () => {
    expect(verifyCodeErrorMessage({ code: "otp_expired", status: 403 })).toMatch(/expired or has already been used/);
    expect(verifyCodeErrorMessage({ status: 429 })).toMatch(/Too many tries/);
    expect(verifyCodeErrorMessage({ name: "AuthRetryableFetchError" })).toMatch(/Could not reach/);
    expect(verifyCodeErrorMessage({ name: "AuthRetryableFetchError", status: 500 })).toMatch(/had a problem/);
    expect(verifyCodeErrorMessage({ status: 400 })).toMatch(/not right/);
  });
});

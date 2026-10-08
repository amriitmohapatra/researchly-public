import { describe, expect, it, vi } from "vitest";
import { withBearer, type CheckResult, type EngineAuth } from "@/lib/engine";
import { errorFromResponse } from "@/lib/errors";

const ok: CheckResult<string> = { ok: true, data: "result" };
const err = (status: number, code: string): CheckResult<string> => ({
  ok: false,
  error: errorFromResponse(status, { error: { code, message: "m", request_id: "r" } }),
});

function auth(over: Partial<EngineAuth> = {}): EngineAuth & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    token: vi.fn(async () => {
      calls.push("token");
      return "t1";
    }),
    refresh: vi.fn(async () => {
      calls.push("refresh");
      return { token: "t2" };
    }),
    signOutLocally: vi.fn(async () => {
      calls.push("signOut");
    }),
    ...over,
  };
}

describe("withBearer: 401 unauthorized → refresh once → retry once", () => {
  it("sends the current token and returns a success untouched", async () => {
    const a = auth();
    const attempt = vi.fn(async () => ok);
    expect(await withBearer(a, attempt)).toBe(ok);
    expect(attempt).toHaveBeenCalledExactlyOnceWith("t1");
    expect(a.calls).toEqual(["token"]);
  });

  it("sends no token when there is no auth (accounts off) or no session", async () => {
    const attempt = vi.fn(async () => ok);
    await withBearer(null, attempt);
    expect(attempt).toHaveBeenLastCalledWith(null);
    await withBearer(auth({ token: async () => null }), attempt);
    expect(attempt).toHaveBeenLastCalledWith(null);
  });

  it("on unauthorized, refreshes and retries with the new token", async () => {
    const a = auth();
    const attempt = vi.fn(async (t: string | null) => (t === "t2" ? ok : err(401, "unauthorized")));
    expect(await withBearer(a, attempt)).toBe(ok);
    expect(attempt.mock.calls.map((c) => c[0])).toEqual(["t1", "t2"]);
    expect(a.calls).toEqual(["token", "refresh"]);
  });

  it("still unauthorized after the retry: signs out locally and says so (never retries anonymously)", async () => {
    const a = auth();
    const attempt = vi.fn<(t: string | null) => Promise<CheckResult<string>>>(async () => err(401, "unauthorized"));
    const r = await withBearer(a, attempt);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.kind).toBe("signed_out");
      expect(r.error.signIn).toBe(true);
    }
    expect(attempt).toHaveBeenCalledTimes(2);
    expect(attempt.mock.calls.every((c) => c[0] !== null)).toBe(true);
    expect(a.calls).toEqual(["token", "refresh", "signOut"]);
  });

  it("a dead session (refresh refused) signs out without a second engine call", async () => {
    const a = auth({ refresh: async () => ({ token: null, transient: false }) });
    const attempt = vi.fn(async () => err(401, "unauthorized"));
    const r = await withBearer(a, attempt);
    expect(!r.ok && r.error.kind).toBe("signed_out");
    expect(attempt).toHaveBeenCalledTimes(1);
    expect(a.signOutLocally).toHaveBeenCalledOnce();
  });

  it("a refresh that fails for a passing reason (offline) keeps the session and is retryable", async () => {
    const a = auth({ refresh: async () => ({ token: null, transient: true }) });
    const r = await withBearer(a, async () => err(401, "unauthorized"));
    expect(!r.ok && r.error.kind).toBe("auth_unavailable");
    expect(!r.ok && r.error.retryable).toBe(true);
    expect(a.signOutLocally).not.toHaveBeenCalled();
  });

  it("does not refresh for other errors, including sign_in_required and auth_unavailable", async () => {
    for (const [status, code] of [
      [401, "sign_in_required"],
      [503, "auth_unavailable"],
      [500, "internal"],
    ] as const) {
      const a = auth();
      const r = await withBearer(a, async () => err(status, code));
      expect(!r.ok && r.error.code).toBe(code);
      expect(a.refresh).not.toHaveBeenCalled();
    }
  });

  it("a non-auth failure on the retry is returned as is (no sign-out)", async () => {
    const a = auth();
    let n = 0;
    const r = await withBearer(a, async () => (++n === 1 ? err(401, "unauthorized") : err(500, "internal")));
    expect(!r.ok && r.error.kind).toBe("server");
    expect(a.signOutLocally).not.toHaveBeenCalled();
  });
});

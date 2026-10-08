import { describe, expect, it } from "vitest";
import { normaliseSupabaseKey, normaliseSupabaseUrl, supabaseConfig } from "@/lib/config";

// Assembled at run time, like the fake secrets below, so secret scanners do
// not take the fixture for a credential.
const KEY = ["sb", "publishable", "AbCdEf123456_-x"].join("_");

describe("Supabase URL", () => {
  it("accepts a hosted project and reduces it to its origin", () => {
    expect(normaliseSupabaseUrl("https://abcdefghij.supabase.co")).toBe("https://abcdefghij.supabase.co");
    expect(normaliseSupabaseUrl(" https://abcdefghij.supabase.co/ ")).toBe("https://abcdefghij.supabase.co");
  });
  it("accepts a local Supabase over http or https", () => {
    expect(normaliseSupabaseUrl("http://localhost:54321")).toBe("http://localhost:54321");
    expect(normaliseSupabaseUrl("http://127.0.0.1:54321")).toBe("http://127.0.0.1:54321");
    expect(normaliseSupabaseUrl("https://localhost:54321")).toBe("https://localhost:54321");
  });
  it("is null when unset", () => {
    expect(normaliseSupabaseUrl(undefined)).toBeNull();
    expect(normaliseSupabaseUrl("  ")).toBeNull();
  });
  it("refuses http for a hosted project", () => {
    expect(() => normaliseSupabaseUrl("http://abcdefghij.supabase.co")).toThrow(/https/);
  });
  it("refuses any host but supabase.co or localhost (it goes into connect-src)", () => {
    expect(() => normaliseSupabaseUrl("https://evil.example.org")).toThrow(/supabase\.co/);
    expect(() => normaliseSupabaseUrl("https://supabase.co.evil.org")).toThrow(/supabase\.co/);
    expect(() => normaliseSupabaseUrl("https://a.b.supabase.co")).toThrow(/supabase\.co/);
    expect(() => normaliseSupabaseUrl("https://supabase.co")).toThrow(/supabase\.co/);
  });
  it("refuses paths, queries, credentials and non-URLs", () => {
    expect(() => normaliseSupabaseUrl("https://abcdefghij.supabase.co/rest/v1")).toThrow(/base URL/);
    expect(() => normaliseSupabaseUrl("https://abcdefghij.supabase.co/?x=1")).toThrow(/base URL/);
    expect(() => normaliseSupabaseUrl("https://user:pw@abcdefghij.supabase.co")).toThrow(/base URL/);
    expect(() => normaliseSupabaseUrl("abcdefghij.supabase.co")).toThrow(/valid absolute URL/);
    expect(() => normaliseSupabaseUrl("javascript:alert(1)")).toThrow();
  });
});

// Fake secret keys, assembled at run time so no secret scanner mistakes the
// fixtures for credentials (the public copy is scanned before it ships).
const fakeSecret = (tail: string) => ["sb", "secret", tail].join("_");

describe("Supabase publishable key", () => {
  it("accepts a publishable key", () => {
    expect(normaliseSupabaseKey(KEY)).toBe(KEY);
    expect(normaliseSupabaseKey(undefined)).toBeNull();
  });
  it("refuses a secret key loudly: it would be published to every visitor", () => {
    expect(() => normaliseSupabaseKey(fakeSecret("AbCdEf123456"))).toThrow(/SECRET/);
  });
  it("refuses anything else, including legacy JWT keys", () => {
    expect(() => normaliseSupabaseKey("eyJhbGciOiJIUzI1NiJ9.e30.x")).toThrow(/sb_publishable_/);
    expect(() => normaliseSupabaseKey("sb_publishable_")).toThrow();
    expect(() => normaliseSupabaseKey("sb_publishable_has space")).toThrow();
  });
});

describe("accounts on/off", () => {
  it("is on only with both values set", () => {
    expect(supabaseConfig("https://abcdefghij.supabase.co", KEY)).toEqual({ url: "https://abcdefghij.supabase.co", key: KEY });
    expect(supabaseConfig(undefined, KEY)).toBeNull();
    expect(supabaseConfig("https://abcdefghij.supabase.co", undefined)).toBeNull();
    expect(supabaseConfig(undefined, undefined)).toBeNull();
  });
  it("still fails on a malformed value when the other is unset", () => {
    expect(() => supabaseConfig("https://evil.example.org", undefined)).toThrow();
    expect(() => supabaseConfig(undefined, fakeSecret("x1234567"))).toThrow();
  });
});

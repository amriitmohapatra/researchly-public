"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { EMAIL_CODE, normaliseCode, sendEmailCode, verifyEmailCode } from "@/lib/auth";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Step =
  | { kind: "email"; problem: string | null; busy: boolean }
  | { kind: "code"; email: string; problem: string | null; busy: boolean; resent: boolean };

/**
 * Sign-in inside the taskpane, by a code sent to the writer's email (S3).
 * No Office dialog and no Microsoft account: the code is typed here, and
 * supabase-js keeps the session in this taskpane's own storage. (A link
 * would open the system browser, not Word.)
 */
export function CodeSignIn({ onDone, onCancel }: { onDone: (email: string) => void; onCancel: () => void }) {
  const [step, setStep] = useState<Step>({ kind: "email", problem: null, busy: false });
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const emailRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const ids = { title: useId(), email: useId(), emailHint: useId(), code: useId(), codeHint: useId(), problem: useId() };

  useEffect(() => {
    if (step.kind === "email") emailRef.current?.focus();
    else codeRef.current?.focus();
  }, [step.kind]);

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    if (step.busy) return;
    const value = email.trim();
    if (!EMAIL.test(value)) {
      setStep({ kind: "email", problem: "Enter your email address, for example name@university.ac.uk.", busy: false });
      emailRef.current?.focus();
      return;
    }
    setStep({ kind: "email", problem: null, busy: true });
    const r = await sendEmailCode(value);
    if (r.ok) {
      setCode("");
      setStep({ kind: "code", email: value, problem: null, busy: false, resent: false });
    } else setStep({ kind: "email", problem: r.message, busy: false });
  };

  const resend = async () => {
    if (step.kind !== "code" || step.busy) return;
    setStep({ ...step, busy: true, problem: null });
    const r = await sendEmailCode(step.email);
    setStep({ ...step, busy: false, resent: r.ok, problem: r.ok ? null : r.message });
  };

  const verify = async (e: FormEvent) => {
    e.preventDefault();
    if (step.kind !== "code" || step.busy) return;
    if (!EMAIL_CODE.test(normaliseCode(code))) {
      setStep({ ...step, problem: "Enter the code from the email: 6 to 10 digits." });
      codeRef.current?.focus();
      return;
    }
    setStep({ ...step, busy: true, problem: null });
    const r = await verifyEmailCode(step.email, code);
    if (r.ok) onDone(step.email);
    else {
      setStep({ ...step, busy: false, problem: r.message });
      requestAnimationFrame(() => codeRef.current?.focus());
    }
  };

  const problem = step.problem;
  const describedBy = (hint: string) => [hint, problem ? ids.problem : null].filter(Boolean).join(" ");

  return (
    <section className="panel tp-signin" aria-labelledby={ids.title} data-testid="code-sign-in">
      <h2 id={ids.title} className="panel-title">
        Sign in to Researchly
      </h2>
      {step.kind === "email" ? (
        <form onSubmit={send} noValidate className="tp-signin-form">
          <p className="muted">
            Signed in, your muted rules, dictionary and Draft or Revise choice follow you between Word and the website.
            Your text is still never stored.
          </p>
          <div className="field">
            <label htmlFor={ids.email} className="field-label">
              Email address
            </label>
            <p id={ids.emailHint} className="help">
              We will email you a sign-in code. No password needed.
            </p>
            <input
              id={ids.email}
              ref={emailRef}
              className="input"
              type="email"
              autoComplete="email"
              inputMode="email"
              spellCheck={false}
              autoCapitalize="off"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (problem) setStep({ kind: "email", problem: null, busy: false });
              }}
              aria-invalid={problem ? true : undefined}
              aria-describedby={describedBy(ids.emailHint)}
              data-testid="code-email"
            />
            {problem ? (
              <p id={ids.problem} className="field-problem" role="alert" data-testid="code-problem">
                {problem}
              </p>
            ) : null}
          </div>
          <div className="tp-row">
            <button type="submit" className="btn btn-primary" aria-disabled={step.busy || undefined} data-testid="code-send">
              {step.busy ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Sending…
                </>
              ) : (
                "Email me a code"
              )}
            </button>
            <button type="button" className="btn btn-quiet" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <form onSubmit={verify} noValidate className="tp-signin-form">
          <p role="status">
            We sent a code to <strong className="break-anywhere">{step.email}</strong>.
            {step.resent ? " A new code is on its way; use the latest one." : ""}
          </p>
          <div className="field">
            <label htmlFor={ids.code} className="field-label">
              Sign-in code
            </label>
            <p id={ids.codeHint} className="help">
              The code in the email, 6 to 10 digits. Not there after a minute? Look in your spam folder.
            </p>
            <input
              id={ids.code}
              ref={codeRef}
              className="input tp-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              spellCheck={false}
              maxLength={14}
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                if (problem) setStep({ ...step, problem: null });
              }}
              aria-invalid={problem ? true : undefined}
              aria-describedby={describedBy(ids.codeHint)}
              data-testid="code-input"
            />
            {problem ? (
              <p id={ids.problem} className="field-problem" role="alert" data-testid="code-problem">
                {problem}
              </p>
            ) : null}
          </div>
          <div className="tp-row">
            <button type="submit" className="btn btn-primary" aria-disabled={step.busy || undefined} data-testid="code-verify">
              {step.busy ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Checking…
                </>
              ) : (
                "Sign in"
              )}
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => void resend()} data-testid="code-resend">
              Send a new code
            </button>
          </div>
          <div className="tp-row">
            <button
              type="button"
              className="btn-link"
              onClick={() => setStep({ kind: "email", problem: null, busy: false })}
            >
              Use a different address
            </button>
            <button type="button" className="btn-link" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

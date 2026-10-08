"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { closeSignIn, sendMagicLink, useAuth } from "@/lib/auth";

type Step = { kind: "form"; problem: string | null } | { kind: "sending" } | { kind: "sent"; email: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Email magic-link sign-in, in a native modal <dialog> (focus is contained,
 * Escape closes, focus returns to the opener). Opened from the header, from
 * the upload control and from "sign in" prompts via lib/auth's openSignIn().
 */
export function SignInDialog() {
  const { auth, dialogOpen, dialogReason, notice } = useAuth();
  const ref = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState("");
  const [step, setStep] = useState<Step>({ kind: "form", problem: null });
  const ids = { title: useId(), email: useId(), hint: useId(), problem: useId() };
  const signedIn = auth.status === "signed_in";

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (dialogOpen && !signedIn && !d.open) {
      setStep({ kind: "form", problem: null });
      d.showModal();
      inputRef.current?.focus();
    } else if ((!dialogOpen || signedIn) && d.open) {
      d.close();
    }
  }, [dialogOpen, signedIn]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (step.kind === "sending") return;
    const value = email.trim();
    if (!EMAIL.test(value)) {
      setStep({ kind: "form", problem: "Enter your email address, for example name@university.ac.uk." });
      inputRef.current?.focus();
      return;
    }
    setStep({ kind: "sending" });
    const r = await sendMagicLink(value);
    if (r.ok) setStep({ kind: "sent", email: value });
    else {
      setStep({ kind: "form", problem: r.message });
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  };

  const problem = step.kind === "form" ? step.problem : null;

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={ids.title}
      onClose={closeSignIn}
      data-testid="sign-in-dialog"
    >
      {step.kind === "sent" ? (
        <div className="dialog-body" role="status">
          <h2 id={ids.title} className="dialog-title">
            Check your email
          </h2>
          <p>
            We sent a sign-in link to <strong className="break-anywhere">{step.email}</strong>. Open it in this
            browser to finish signing in. The link works once.
          </p>
          <p className="muted">Not there after a minute? Look in your spam folder, or send it again.</p>
          <div className="dialog-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setStep({ kind: "form", problem: null })}>
              Use a different address
            </button>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => {
                setStep({ kind: "sending" });
                void sendMagicLink(step.email).then((r) =>
                  setStep(r.ok ? { kind: "sent", email: step.email } : { kind: "form", problem: r.message }),
                );
              }}
            >
              Send again
            </button>
            <button type="button" className="btn btn-quiet" onClick={closeSignIn}>
              Close
            </button>
          </div>
        </div>
      ) : (
        <form className="dialog-body" onSubmit={onSubmit} noValidate>
          <h2 id={ids.title} className="dialog-title">
            Sign in to Researchly
          </h2>
          {notice ? (
            <p className="notice notice-quiet dialog-notice" data-testid="sign-in-notice">
              {notice}
            </p>
          ) : null}
          {dialogReason ? <p className="dialog-reason">{dialogReason}</p> : null}
          <p className="muted">
            An account lets you check whole files and keeps your muted rules and dictionary on every device. Your text
            is still never stored.
          </p>
          <div className="field">
            <label htmlFor={ids.email} className="field-label">
              Email address
            </label>
            <p id={ids.hint} className="help">
              We will email you a link. No password needed.
            </p>
            <input
              id={ids.email}
              ref={inputRef}
              className="input"
              type="email"
              name="email"
              autoComplete="email"
              inputMode="email"
              spellCheck={false}
              autoCapitalize="off"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (problem) setStep({ kind: "form", problem: null });
              }}
              aria-invalid={problem ? true : undefined}
              aria-describedby={[ids.hint, problem ? ids.problem : null].filter(Boolean).join(" ")}
              data-testid="sign-in-email"
            />
            {problem ? (
              <p id={ids.problem} className="field-problem" role="alert" data-testid="sign-in-problem">
                {problem}
              </p>
            ) : null}
          </div>
          <div className="dialog-actions">
            <button
              type="submit"
              className="btn btn-primary"
              aria-disabled={step.kind === "sending" || undefined}
              data-testid="sign-in-send"
            >
              {step.kind === "sending" ? (
                <>
                  <span className="spinner" aria-hidden="true" />
                  Sending…
                </>
              ) : (
                "Email me a sign-in link"
              )}
            </button>
            <button type="button" className="btn btn-quiet" onClick={closeSignIn}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}

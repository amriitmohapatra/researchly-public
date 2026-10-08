"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { openSignIn, signOut, useAuth } from "@/lib/auth";
import { SignInDialog } from "./SignInDialog";

/**
 * The header's account control (only in a build with accounts).
 * Signed out: a "Sign in" button. Signed in: a disclosure showing the email,
 * a Settings link and Sign out. It is a disclosure (button + panel of normal
 * links and buttons), not an ARIA menu, so Tab and Enter work as everywhere
 * else; Escape closes it and returns focus to the button.
 */
export function AccountMenu() {
  const { auth } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  if (auth.status === "off") return null;

  let control;
  if (auth.status === "loading") {
    // Holds the space so the header does not jump when the session is known.
    control = <span className="account-placeholder" aria-hidden="true" />;
  } else if (auth.status === "signed_out") {
    control = (
      <button type="button" className="btn btn-secondary btn-compact" onClick={() => openSignIn()} data-testid="sign-in">
        Sign in
      </button>
    );
  } else {
    control = (
      <div
        className="account"
        ref={wrapRef}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.stopPropagation();
            setOpen(false);
            buttonRef.current?.focus();
          }
        }}
        onBlur={(e) => {
          if (open && !e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false);
        }}
      >
        <button
          ref={buttonRef}
          type="button"
          className="account-button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          data-testid="account-button"
        >
          <span className="sr-only">Account: </span>
          <span className="account-email">{auth.email}</span>
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false" className="account-caret">
            <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
        <div id={panelId} className="account-panel" hidden={!open} data-testid="account-panel">
          <p className="account-who">
            <span className="muted">Signed in as</span>
            <span className="account-who-email">{auth.email}</span>
          </p>
          <ul className="account-links">
            <li>
              <Link href="/settings" className="account-item" onClick={() => setOpen(false)}>
                Settings and dictionary
              </Link>
            </li>
            <li>
              <Link href="/progress" className="account-item" onClick={() => setOpen(false)} data-testid="nav-progress">
                Progress
              </Link>
            </li>
            <li>
              <Link href="/label" className="account-item" onClick={() => setOpen(false)} data-testid="nav-label">
                Label flags
              </Link>
            </li>
            <li>
              <button
                type="button"
                className="account-item"
                aria-disabled={busy || undefined}
                onClick={async () => {
                  if (busy) return;
                  setBusy(true);
                  await signOut();
                  setBusy(false);
                  setOpen(false);
                }}
                data-testid="sign-out"
              >
                Sign out
              </button>
            </li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <>
      {control}
      <SignInDialog />
    </>
  );
}

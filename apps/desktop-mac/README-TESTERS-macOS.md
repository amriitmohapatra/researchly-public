# Researchly for macOS — Tester Guide (v0.7)

Researchly is a writing assistant for **scientific writing** that works
in every app on your Mac — Word, browsers (Overleaf, Google Docs), Mail,
Notes. Everything runs locally: no account, no cloud, no AI generation;
your unpublished work never leaves your machine.

## Install

1. Open `Researchly.dmg` and drag **Researchly** to Applications.
2. First launch: **right-click the app → Open → Open** (it's a personal
   build, not App-Store signed — this is only needed once).
   - If macOS says the app "is damaged", run this once in Terminal and
     retry:  `xattr -cr /Applications/Researchly.app`
3. macOS will ask for **Accessibility** permission → System Settings →
   Privacy & Security → Accessibility → enable Researchly. This is what
   lets it read your selected text and paste rewrites back.
4. An **R** appears in the menu bar. First use takes ~15 s (model loads).

## Use — two hotkeys, anywhere

- Select text in ANY app → **⌘⇧R** → floating panel with suggestions
  (each with a "Why?" tracing to writing scholarship).
- Select a clunky paragraph → **⌘⇧P** → a marked-up rewrite →
  **Replace selection** pastes it back where you were typing.
- Menu bar → **Live watching (beta)**: a small "R n" count badge follows
  the field you're typing in (native apps only; browsers don't expose
  text — use the hotkeys there). Off by default.

## What feedback helps most

1. **False positives** — flagged text that's actually fine (send the
   sentence + the rule ID shown on the card).
2. **Misses** — errors it should have caught.
3. Apps where the hotkeys don't capture your selection (tell us which).

## Troubleshooting

- Hotkeys do nothing → Accessibility permission missing (step 3), then
  quit and reopen Researchly.
- "No selection" though text is selected → that app resists both capture
  methods; tell us which app.
- Panel empty on first try → wait for the model to warm up, retry.

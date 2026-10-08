# Researchly for VS Code / Positron

The Researchly checker inside your editor: underlined suggestions as you
write `.qmd`, `.md`, `.Rmd`, `.tex`, or plain-text files, with quick fixes.
Same engine, same rules, same section awareness as the CLI and the Word
add-in — running entirely on your machine via the Researchly language
server (LSP).

## Install (Mac)

```bash
# 1. one-time server dependency, in the Python that has spaCy:
pip install 'pygls>=1.3,<2'

# 2. install the pre-bundled extension (no npm needed):
cd prototype/vscode-extension
bash install-vscode.sh

# 3. restart VS Code (or Positron)
```

Open any `.qmd` / `.md` / `.tex` file. After a moment (the first check
loads the spaCy model) suggestions appear as underlines:

- **Warning** (yellow) = Correction
- **Information** (blue) = Improvement / Convention — the message is tagged
  with the type and the section it fired in (e.g. `[convention] … · §methods`)
- **Hint** (dots) = Preference (only if enabled in `.researchly.toml`)

Hover an underline for the message; `Cmd+.` opens quick fixes:
- **replace with '…'** for suggestions with a concrete fix
- **mute rule Xnnn** — writes the rule into `.researchly.toml` next to your
  file, so the mute travels with the project (and works in the CLI too)

The Problems panel (`Cmd+Shift+M`) lists everything, filterable by
`researchly`.

## Settings

| Setting | Default | |
|---|---|---|
| `researchly.pythonPath` | `python3` | interpreter that has spaCy + pygls |
| `researchly.prototypePath` | `~/Documents/Researchly/prototype` | folder containing the `researchly` package |

Command palette: **Researchly: Restart language server** after changing
settings or updating the rules.

## Per-project configuration

`.researchly.toml` in the file's folder (or workspace root):

```toml
[rules]
disable = ["W203"]
show_preferences = false
```

## Quarto notes

Code chunks, YAML front matter, inline code, `$math$`, and `@citations`
are masked before checking — they are never flagged, and positions map
exactly to your source. Use `#` headings ("## Methods") and the
section-aware rules calibrate accordingly.

## Troubleshooting

- **No underlines** → check the "Researchly" output channel (View → Output).
  Most common: `pygls` not installed in the Python that `python3` resolves
  to, or `prototypePath` pointing at the wrong folder.
- **Wrong Python** → set `researchly.pythonPath` to the full path (e.g.
  `/usr/local/bin/python3.10`), then run *Researchly: Restart language
  server*.
- Works in editors beyond VS Code: `harper`-style LSP clients in Neovim,
  Helix, Emacs, or Zed can launch `python3 -m researchly.lsp` directly
  (cwd = the prototype folder).

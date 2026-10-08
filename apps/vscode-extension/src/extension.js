/* Researchly VS Code extension: thin client for the local LSP server.
 * All analysis happens in the Python server on this machine. */

const os = require("os");
const path = require("path");
const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

let client;

function resolveHome(p) {
  if (!p) return p;
  if (p === "~") return os.homedir();
  if (p.startsWith("~/")) return path.join(os.homedir(), p.slice(2));
  return p;
}

function buildClient() {
  const cfg = vscode.workspace.getConfiguration("researchly");
  const python = cfg.get("pythonPath") || "python3";
  const cwd = resolveHome(cfg.get("prototypePath"));

  const serverOptions = {
    command: python,
    args: ["-m", "researchly.lsp"],
    options: { cwd },
    transport: TransportKind.stdio,
  };

  const clientOptions = {
    documentSelector: [
      { scheme: "file", language: "markdown" },
      { scheme: "file", language: "quarto" },
      { scheme: "file", language: "latex" },
      { scheme: "file", language: "tex" },
      { scheme: "file", language: "rmd" },
      { scheme: "file", language: "plaintext" },
    ],
    outputChannelName: "Researchly",
  };

  return new LanguageClient(
    "researchly",
    "Researchly",
    serverOptions,
    clientOptions
  );
}

async function start(context) {
  client = buildClient();
  try {
    await client.start();
  } catch (e) {
    vscode.window.showErrorMessage(
      "Researchly: could not start the language server. Check " +
        "researchly.pythonPath / researchly.prototypePath in Settings, and " +
        "that `pip install pygls` was run. (" + (e.message || e) + ")"
    );
  }
}

function activate(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("researchly.restart", async () => {
      if (client) await client.stop().catch(() => {});
      await start(context);
      vscode.window.showInformationMessage("Researchly: server restarted.");
    })
  );
  start(context);
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };

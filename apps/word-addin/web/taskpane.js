/* Researchly Word taskpane.
 *
 * Reads the document via Office JS, sends paragraphs (text + style) to the
 * LOCAL server (same origin), renders typed suggestions, and lets the user
 * jump to / fix / dismiss / mute. Fixes can be applied as tracked changes.
 * Design principles (from the project research): never silently edit,
 * explain everything, preferences off by default, mute is first-class.
 */

/* global Office, Word */

const $ = (id) => document.getElementById(id);

const state = {
  serverOk: false,
  checking: false,
  dismissed: new Set(),        // per-session: rule|para|start keys
  // Muted rules live in the SHARED config (~/.researchly/config.toml) via
  // the server's /config endpoint — never in localStorage, where no other
  // surface could see them (the W0/W2 parity guarantee).
  muted: new Set(),
  config: null,                // last resolved config from the server
  health: null,                // last tier statuses from the server
  lastText: "",
  autoTimer: null,
  data: null,
};

Office.onReady(() => {
  // On Word versions without WordApi 1.4, tracked-change application is
  // unavailable — say so instead of silently applying untracked.
  try {
    if (!Office.context.requirements.isSetSupported("WordApi", "1.4")) {
      const lbl = $("trackChk").parentElement.querySelector("span");
      if (lbl) lbl.textContent =
        "apply fixes as tracked changes (unavailable in this Word version)";
      $("trackChk").checked = false;
      $("trackChk").disabled = true;
    }
  } catch {}
  initTabs();
  $("checkBtn").onclick = () => runCheck();
  $("reviewBtn").onclick = () => runReview();
  $("polishBtn").onclick = () => runPolish();
  $("polishDiscard").onclick = () => $("polishPanel").classList.add("hidden");
  $("autoChk").onchange = toggleAuto;
  $("prefChk").onchange = () =>
    saveSetting({ show_preferences: $("prefChk").checked }).then(runCheck);
  $("probeBtn").onclick = () => probeGrammar();
  initSettingsHandlers();
  ping().then(() => { migrateLocalStorageMutes().then(loadConfig); });
  setInterval(ping, 15000);
});

/* ---------------- tabs ---------------- */

function initTabs() {
  document.querySelectorAll("#tabs .tab").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#tabs .tab").forEach((b) =>
        b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tabpane").forEach((p) =>
        p.classList.add("hidden"));
      $(`pane-${btn.dataset.tab}`).classList.remove("hidden");
      if (btn.dataset.tab === "settings" || btn.dataset.tab === "health") {
        loadConfig();
      }
    };
  });
}

/* ---------------- shared config (the ONLY settings store) --------------- */

async function loadConfig() {
  if (!state.serverOk) return;
  try {
    const r = await fetch("/status");
    const j = await r.json();
    applyConfig(j.config, j.health);
  } catch {}
}

function applyConfig(config, health) {
  if (!config) return;
  state.config = config;
  state.muted = new Set(config.disabled || []);
  if (health) state.health = health;
  // sync every control that mirrors a shared setting
  $("prefChk").checked = !!config.show_preferences;
  $("setPrefs").checked = !!config.show_preferences;
  $("setDocType").value = config.document_type || "auto";
  $("setAggr").value = config.aggressiveness || "standard";
  $("setLocale").value = config.locale || "en-US";
  $("setGrammar").checked = config.grammar_tier !== false;
  $("setGec").checked = config.gec_tier === true;
  renderMutedList();
  if (state.health) renderHealthList(state.health);
  if (state.data) render(state.data);
}

async function saveSetting(patch) {
  try {
    const r = await fetch("/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    applyConfig(j.config);
    $("settingsMsg").textContent =
      "Saved — shared with every Researchly surface.";
    return j;
  } catch (e) {
    $("settingsMsg").textContent =
      "Could not save: " + (e.message || e);
    return null;
  }
}

function initSettingsHandlers() {
  $("setDocType").onchange = () =>
    saveSetting({ document_type: $("setDocType").value });
  $("setAggr").onchange = () =>
    saveSetting({ aggressiveness: $("setAggr").value });
  $("setLocale").onchange = () =>
    saveSetting({ locale: $("setLocale").value });
  $("setPrefs").onchange = () =>
    saveSetting({ show_preferences: $("setPrefs").checked });
  $("setGrammar").onchange = () =>
    saveSetting({ grammar_tier: $("setGrammar").checked });
  $("setGec").onchange = () =>
    saveSetting({ gec_tier: $("setGec").checked });
}

async function muteRule(ruleId) {
  const j = await saveSetting({ mute: ruleId });
  if (j && state.data) render(state.data);
}

async function unmuteRule(ruleId) {
  const j = await saveSetting({ unmute: ruleId });
  if (j && state.data) render(state.data);
}

async function unmuteAll() {
  // clear the disabled list in the shared config in one write
  const j = await saveSetting({ disabled: [] });
  if (j) runCheck();
}

/**
 * One-time migration: earlier builds kept muted rules in this taskpane's
 * localStorage, invisible to every other surface. Move them into the
 * shared config, then delete the key so this never runs again.
 */
async function migrateLocalStorageMutes() {
  let legacy = [];
  try {
    legacy = JSON.parse(localStorage.getItem("researchly.muted") || "[]");
  } catch {}
  if (!legacy.length) {
    try { localStorage.removeItem("researchly.muted"); } catch {}
    return;
  }
  for (const ruleId of legacy) {
    try { await saveSetting({ mute: ruleId }); } catch {}
  }
  try { localStorage.removeItem("researchly.muted"); } catch {}
}

async function ping() {
  try {
    const r = await fetch("/ping");
    const j = await r.json();
    state.serverOk = !!j.ok;
    $("status").textContent = `local server connected · ${j.rules} rules · all analysis on this computer`;
    $("status").className = "status ok";
    $("checkBtn").disabled = false;
  } catch {
    state.serverOk = false;
    $("status").textContent = "local server not running — start it with:  python server.py";
    $("status").className = "status err";
    $("checkBtn").disabled = true;
  }
  $("polishBtn").disabled = !state.serverOk;
  $("reviewBtn").disabled = !state.serverOk;
}

/* ---------------- review (critical-reader report) ---------------- */

async function runReview() {
  if (!state.serverOk) return;
  $("reviewBtn").textContent = "Reading…";
  try {
    const paragraphs = await getParagraphs();
    const resp = await fetch("/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paragraphs }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    $("reviewOut").textContent = data.report;
    $("reviewOut").classList.remove("hidden");
  } catch (e) {
    $("reviewOut").textContent = "Review failed: " + (e.message || e);
    $("reviewOut").classList.remove("hidden");
  } finally {
    $("reviewBtn").textContent = "Run reviewer's brief";
  }
}

/* ---------------- health tab ---------------- */

function renderHealthList(health) {
  const el = $("healthList");
  if (!el) return;
  el.innerHTML = (health || [])
    .map((t) => {
      const cls = t.ok ? "ok" : (t.state === "disabled" ? "off" : "down");
      return `<div class="health-row ${cls}">
        <b>${escapeHtml(t.label)}</b> — ${escapeHtml(t.state)}
        <div class="dim">${escapeHtml(t.detail || "")}</div>
        ${t.remedy ? `<code>${escapeHtml(t.remedy)}</code>` : ""}
      </div>`;
    })
    .join("");
}

async function probeGrammar() {
  $("healthMsg").textContent =
    "Probing — the first run may download LanguageTool (~200 MB)…";
  $("probeBtn").disabled = true;
  try {
    const r = await fetch("/status?probe=1");
    const j = await r.json();
    applyConfig(j.config, j.health);
    $("healthMsg").textContent = j.summary || "done";
  } catch (e) {
    $("healthMsg").textContent = "Probe failed: " + (e.message || e);
  } finally {
    $("probeBtn").disabled = false;
  }
}

/* ---------------- settings: muted-rules list ---------------- */

function renderMutedList() {
  const el = $("mutedList");
  if (!el) return;
  if (!state.muted.size) {
    el.textContent = "none";
    return;
  }
  el.innerHTML = [...state.muted]
    .sort()
    .map(
      (id) =>
        `<span class="muted-chip">${escapeHtml(id)} ` +
        `<a data-rule="${escapeHtml(id)}" class="unmute-one">unmute</a></span>`
    )
    .join(" ");
  el.querySelectorAll(".unmute-one").forEach((a) => {
    a.onclick = () => unmuteRule(a.dataset.rule);
  });
}

/* ---------------- polish (deterministic rewrite) ---------------- */

async function runPolish() {
  if (!state.serverOk) return;
  $("polishBtn").textContent = "Polishing…";
  try {
    const selection = await Word.run(async (ctx) => {
      const sel = ctx.document.getSelection();
      sel.load("text");
      await ctx.sync();
      return sel.text || "";
    });
    if (!selection.trim()) {
      showPolishMessage(
        "Select a sentence or paragraph in the document first.");
      return;
    }
    const resp = await fetch("/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: selection }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    renderPolish(data);
  } catch (e) {
    showPolishMessage("Polish failed: " + escapeHtml(String(e.message || e)));
  } finally {
    $("polishBtn").textContent = "Polish selection";
  }
}

function showPolishMessage(msg) {
  $("polishDiff").innerHTML = `<span class="dim-note">${msg}</span>`;
  $("polishEdits").innerHTML = "";
  $("polishInsert").style.display = "none";
  $("polishPanel").classList.remove("hidden");
}

function renderPolish(data) {
  if (!data.changed) {
    const notes = (data.notes || []).length
      ? `<br><br>Remaining observations for your judgement:<br>` +
        data.notes.slice(0, 5).map(escapeHtml).join("<br>")
      : "";
    showPolishMessage("Nothing to safely rewrite here — the sentence-level "
      + "edits all check out." + notes);
    return;
  }
  $("polishDiff").innerHTML = data.segments
    .map((s) => {
      const t = escapeHtml(s.text);
      if (s.op === "del") return `<del>${t}</del>`;
      if (s.op === "ins") return `<ins>${t}</ins>`;
      return t;
    })
    .join("");
  $("polishEdits").innerHTML = data.edits
    .map(
      (e) =>
        `<div><b>${e.rule_id}</b> ${escapeHtml(e.rule_name)}: ` +
        `“${escapeHtml(e.before)}” → “${escapeHtml(e.after)}”</div>`
    )
    .join("") +
    ((data.notes || []).length
      ? `<div style="margin-top:6px">Left for your judgement: ` +
        `${data.notes.length} flag${data.notes.length === 1 ? "" : "s"} ` +
        `(run Check document to see them)</div>`
      : "");
  $("polishInsert").style.display = "";
  $("polishInsert").onclick = () => insertPolished(data.rewritten);
  $("polishPanel").classList.remove("hidden");
}

function insertPolished(text) {
  Word.run(async (ctx) => {
    const sel = ctx.document.getSelection();
    if (await overlapsField(ctx, sel)) {
      throw new Error(
        "the selection contains a citation or other Word field — " +
        "rewriting it would break the field");
    }
    const prior = await beginTracking(ctx);
    try {
      sel.insertText(text, Word.InsertLocation.replace);
      await ctx.sync();
    } finally {
      await endTracking(ctx, prior);
    }
    $("polishPanel").classList.add("hidden");
  }).catch((e) =>
    showPolishMessage(
      "Could not insert — reselect the passage and try again. (" +
        escapeHtml(String(e.message || e)) + ")"
    )
  );
}

function toggleAuto() {
  if ($("autoChk").checked) {
    state.autoTimer = setInterval(async () => {
      if (state.checking || !state.serverOk) return;
      const text = await quickText();
      if (text !== null && text !== state.lastText) runCheck();
    }, 4000);
  } else {
    clearInterval(state.autoTimer);
  }
}

/**
 * Word returns body.text with \r paragraph separators, while we join the
 * paragraph array with \n. The old auto-recheck compared those two strings
 * directly, so they could never be equal and a full document check fired
 * every 4 seconds whether or not anything had been typed.
 */
function normalizeBody(t) {
  return (t || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\u000B/g, "\n")   // Word's soft line break
    .replace(/\n+/g, "\n")
    .trim();
}

function quickText() {
  return Word.run(async (ctx) => {
    const body = ctx.document.body;
    body.load("text");
    await ctx.sync();
    return normalizeBody(body.text);
  }).catch(() => null);
}

async function getParagraphs() {
  return Word.run(async (ctx) => {
    const paras = ctx.document.body.paragraphs;
    paras.load(
      "items/text,items/styleBuiltIn,items/style,items/tableNestingLevel");
    await ctx.sync();
    return paras.items.map((p) => ({
      text: p.text || "",
      style:
        p.styleBuiltIn && p.styleBuiltIn !== "Other"
          ? p.styleBuiltIn
          : p.style || "",
      // Table cells are not prose. Joined in as if they were, they skewed
      // sentence-length and passive-voice metrics and could carry a section
      // heading's meaning into a data cell.
      kind: p.tableNestingLevel > 0 ? "table" : "body",
    }));
  });
}

async function runCheck() {
  if (!state.serverOk || state.checking) return;
  state.checking = true;
  $("checkBtn").textContent = "Checking…";
  try {
    const paragraphs = await getParagraphs();
    state.lastText = normalizeBody(paragraphs.map((p) => p.text).join("\n"));
    // No `disabled` override: the server resolves the shared config, so a
    // rule muted here (or in any other surface) is muted for this check.
    const resp = await fetch("/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paragraphs,
        show_preferences: $("prefChk").checked,
      }),
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    state.data = data;
    render(data);
  } catch (e) {
    $("results").innerHTML =
      `<div class="empty"><p>Check failed.</p><p class="dim">${escapeHtml(
        String(e.message || e)
      )}</p></div>`;
  } finally {
    state.checking = false;
    $("checkBtn").textContent = "Check document";
  }
}

/* ---------------- telemetry (local server only, never leaves the Mac) --- */

function tele(event, s, n) {
  try {
    fetch("/telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        events: [{ event, rule: s.rule_id, section: s.section, n: n || 1 }],
      }),
    }).catch(() => {});
  } catch {
    /* telemetry must never break the UI */
  }
}

function teleShownBatch(visible) {
  const byRule = {};
  visible.forEach((s) => {
    const k = `${s.rule_id}|${s.section}`;
    byRule[k] = byRule[k] || { event: "shown", rule: s.rule_id, section: s.section, n: 0 };
    byRule[k].n += 1;
  });
  const events = Object.values(byRule);
  if (!events.length) return;
  try {
    fetch("/telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    }).catch(() => {});
  } catch {}
}

/* ---------------- rendering ---------------- */

let lastShownSignature = "";

function render(data) {
  const visible = data.suggestions.filter(
    (s) => !state.dismissed.has(key(s)) && !state.muted.has(s.rule_id)
  );

  // log "shown" once per check result (not on re-renders after dismiss)
  const sig = visible.map(key).join(",");
  if (sig !== lastShownSignature) {
    lastShownSignature = sig;
    teleShownBatch(visible);
  }

  const cats = ["correction", "improvement", "convention", "preference"];
  $("summary").innerHTML = cats
    .map((c) => {
      const n = visible.filter((s) => s.category === c).length;
      return `<span class="chip ${c}${n ? "" : " zero"}">${n} ${c}${
        n === 1 ? "" : "s"
      }</span>`;
    })
    .join("");
  $("summary").classList.remove("hidden");

  renderMutedLine();
  renderTiers(data.health);

  if (!visible.length) {
    $("results").innerHTML =
      `<div class="empty"><p>Nothing to flag${
        data.hidden_preferences
          ? ` (${data.hidden_preferences} preference notes hidden)`
          : ""
      }.</p><p class="dim">Sections detected: ${
        (data.sections_detected || []).join(", ") || "none — using unknown"
      }</p>${coverageNote(data.coverage)}</div>`;
  } else {
    $("results").innerHTML = visible.map(cardHtml).join("");
    visible.forEach((s) => {
      const el = $(`card-${key(s)}`);
      el.querySelector(".flagged").onclick = () => { tele("goto", s); goTo(s); };
      el.querySelector(".goto").onclick = () => { tele("goto", s); goTo(s); };
      const applyBtn = el.querySelector(".apply");
      if (applyBtn) applyBtn.onclick = () => { tele("applied", s); applyFix(s, el); };
      const dictBtn = el.querySelector(".adddict");
      if (dictBtn) dictBtn.onclick = () => addToDictionary(s, el);
      el.querySelector(".dismiss").onclick = () => {
        tele("dismissed", s);
        state.dismissed.add(key(s));
        render(state.data);
      };
      el.querySelector(".mute").onclick = () => {
        tele("muted", s);
        state.muted.add(s.rule_id);   // optimistic; confirmed by /config
        render(state.data);
        muteRule(s.rule_id);
      };
      el.querySelector(".whytoggle").onclick = () =>
        el.classList.toggle("open");
    });
  }

  const m = data.metrics;
  if (m) {
    const passive = Object.entries(m.passive_share_by_section || {})
      .map(([k, v]) => `${k} ${Math.round(v * 100)}%`)
      .join(" · ");
    $("metrics").innerHTML =
      `${m.sentences} sentences · mean ${m.mean_sentence_len} words · ` +
      `${m.long_sentences} over 50 · nominalizations ${m.nominalizations_per_100w}/100w · ` +
      `hedges ${m.hedges_per_100w}/100w · boosters ${m.boosters_per_100w ?? "?"}/100w` +
      (m.hedge_booster_balance ? `<br>calibration: ${m.hedge_booster_balance}` : "") +
      (passive ? `<br>passive by section: ${passive}` : "") +
      `<br><i>a read-out, not a score — Methods is allowed its passives</i>`;
    $("metrics").classList.remove("hidden");
  }
}

function cardHtml(s) {
  const hasFix = s.replacement !== null && s.replacement !== undefined;
  const fix = hasFix
    ? `<div class="fix">fix: ${
        s.replacement.length ? "‘" + escapeHtml(s.replacement) + "’"
                             : "(delete)"
      }</div>`
    : "";
  const applyBtn = hasFix
    ? `<button class="apply">${
        s.replacement.length ? "Apply fix" : "Delete phrase"
      }</button>`
    : "";
  const dictBtn =
    s.rule_id === "S001"
      ? `<button class="adddict">Add to dictionary</button>`
      : "";
  return `
  <div class="card ${s.category}" id="card-${key(s)}">
    <div class="top">
      <span class="rule-tag">${s.category} · ${s.rule_id} ${escapeHtml(
        s.rule_name
      )}</span>
      <span class="section-tag">§${s.section}</span>
    </div>
    <div class="flagged" title="Click to locate in document">${escapeHtml(
      truncate(s.text, 160)
    )}</div>
    <div class="msg">${escapeHtml(s.message)}</div>
    ${fix}
    <div class="actions">
      <button class="goto">Go to</button>
      ${applyBtn}
      ${dictBtn}
      <button class="dismiss">Dismiss</button>
      <button class="mute">Mute rule</button>
      <button class="whytoggle">Why?</button>
    </div>
    <div class="why">${escapeHtml(s.why)}</div>
  </div>`;
}

function renderMutedLine() {
  if (!state.muted.size) {
    $("muted").classList.add("hidden");
    return;
  }
  $("muted").innerHTML = `muted rules: ${[...state.muted].join(", ")} — <a id="unmute">unmute all</a>`;
  $("muted").classList.remove("hidden");
  $("unmute").onclick = () => unmuteAll();
}

/**
 * Name any checking tier that is NOT running. Silence used to mean either
 * "your prose is clean" or "the grammar engine never started", with no way
 * to tell them apart — on this machine LanguageTool had never once run.
 */
function renderTiers(health) {
  const el = $("tiers");
  if (!el) return;
  const down = (health || []).filter(
    (t) => !t.ok && (t.remedy || t.state === "disabled" || t.state === "error")
  );
  if (!down.length) {
    el.classList.add("hidden");
    el.innerHTML = "";
    return;
  }
  el.innerHTML = down
    .map(
      (t) =>
        `<div><b>${escapeHtml(t.label)} checking is off</b> — ${escapeHtml(
          t.detail || ""
        )}${t.remedy ? `<br><code>${escapeHtml(t.remedy)}</code>` : ""}</div>`
    )
    .join("");
  el.classList.remove("hidden");
}

/** What Office JS does not hand us, said out loud rather than left implied. */
function coverageNote(coverage) {
  if (!coverage || !coverage.not_checked) return "";
  return `<p class="dim">Checked ${coverage.paragraphs} paragraph${
    coverage.paragraphs === 1 ? "" : "s"
  } of body text. Not checked: ${coverage.not_checked.join(", ")}.</p>`;
}

/* ---------------- Word actions ---------------- */

function canTrackChanges() {
  try {
    return Office.context.requirements.isSetSupported("WordApi", "1.4");
  } catch {
    return false;
  }
}

async function beginTracking(ctx) {
  // IMPORTANT: setting changeTrackingMode on Word versions without
  // WordApi 1.4 does not throw here — it fails the whole batch at
  // ctx.sync(), which used to kill every Apply. Gate it properly.
  if (!$("trackChk").checked || !canTrackChanges()) return null;
  ctx.document.load("changeTrackingMode");
  await ctx.sync();
  const prior = ctx.document.changeTrackingMode;
  if (prior !== Word.ChangeTrackingMode.trackAll) {
    ctx.document.changeTrackingMode = Word.ChangeTrackingMode.trackAll;
  }
  return prior;
}

async function endTracking(ctx, prior) {
  // Restore whatever the writer had. We used to switch Track Changes on at
  // the first Apply and never switch it back, silently leaving it on for the
  // rest of the document's life.
  if (prior === null || prior === undefined) return;
  if (prior === Word.ChangeTrackingMode.trackAll) return;
  ctx.document.changeTrackingMode = prior;
  await ctx.sync();
}

/**
 * Locate a suggestion's range, or explain why we will not touch it.
 *
 * Word has no offset-addressable API, so a span has to be re-found by
 * searching. The old version searched for a 180-character *prefix*, clamped
 * the occurrence index with Math.min, and fell back to the first match in
 * the whole document — so on a repeated phrase it would silently rewrite the
 * wrong copy. Nothing ever verified that the text at the recorded position
 * was still what had been checked.
 *
 * Returns {range} or {error}.
 */
async function findRange(ctx, s) {
  if (!s.snippet) return { error: "nothing to search for" };
  if (s.exact === false) {
    return {
      error:
        "this span is too long for Word's search — use Go to and edit it " +
        "by hand",
    };
  }

  const paras = ctx.document.body.paragraphs;
  paras.load("items/text");
  await ctx.sync();

  const para = paras.items[s.para];
  const expected = s.expected !== undefined ? s.expected : s.snippet;

  // Is the document still what we checked, right here? This is the guard
  // that makes the occurrence index trustworthy.
  const unchanged =
    para &&
    para.text.substring(s.start_in_para, s.end_in_para) === expected;

  if (unchanged) {
    const results = para.search(s.snippet, { matchCase: true });
    results.load("items");
    await ctx.sync();
    if (results.items.length > s.occurrence) {
      return { range: results.items[s.occurrence] };
    }
    // The paragraph text matched but the search disagrees (wildcards,
    // field codes). Refuse rather than guess at an index.
    return { error: "could not locate that text precisely — run Check again" };
  }

  // The paragraph moved or was edited. A document-wide search is only safe
  // when it is unambiguous.
  const bodyResults = ctx.document.body.search(s.snippet, { matchCase: true });
  bodyResults.load("items");
  await ctx.sync();
  if (bodyResults.items.length === 1) {
    return { range: bodyResults.items[0] };
  }
  if (bodyResults.items.length === 0) {
    return { error: "that text is no longer in the document — run Check again" };
  }
  return {
    error:
      `the document changed and "${truncate(s.snippet, 30)}" appears ` +
      `${bodyResults.items.length} times — run Check again so the right ` +
      `one can be identified`,
  };
}

/**
 * Refuse to edit across a Word field. A Zotero/Mendeley/EndNote citation is
 * a field whose *result* is the text we see; insertText over it destroys the
 * field code and degrades a live citation to dead text.
 */
async function overlapsField(ctx, range) {
  if (!Office.context.requirements.isSetSupported("WordApi", "1.4")) {
    return false;
  }
  try {
    const fields = range.fields;
    fields.load("items");
    await ctx.sync();
    return fields.items.length > 0;
  } catch {
    return false; // older builds: no field API, proceed as before
  }
}

function goTo(s) {
  Word.run(async (ctx) => {
    const found = await findRange(ctx, s);
    if (found.range) {
      found.range.select();
      await ctx.sync();
    }
  }).catch(() => {});
}

function applyFix(s, el) {
  Word.run(async (ctx) => {
    const found = await findRange(ctx, s);
    if (found.error) throw new Error(found.error);
    const range = found.range;

    if (await overlapsField(ctx, range)) {
      throw new Error(
        "that text sits inside a citation or other Word field — applying " +
        "here would break the field, so it has been left alone");
    }

    const prior = await beginTracking(ctx);
    try {
      range.insertText(s.replacement || "", Word.InsertLocation.replace);
      try {
        range.select();
      } catch {}
      await ctx.sync();
    } finally {
      await endTracking(ctx, prior);
    }
    state.dismissed.add(key(s));
    render(state.data);
  }).catch((e) => {
    el.querySelector(".msg").textContent =
      "Could not apply: " + (e.message || e);
    tele("apply_failed", s);
  });
}

function addToDictionary(s, el) {
  fetch("/dictionary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word: s.text }),
  })
    .then((r) => r.json())
    .then((j) => {
      if (j.error) throw new Error(j.error);
      // hide every card flagging the same word, then re-check
      state.data.suggestions
        .filter(
          (x) =>
            x.rule_id === "S001" &&
            x.text.toLowerCase() === s.text.toLowerCase()
        )
        .forEach((x) => state.dismissed.add(key(x)));
      render(state.data);
      runCheck();
    })
    .catch((e) => {
      el.querySelector(".msg").textContent =
        "Could not save to dictionary: " + (e.message || e);
    });
}

/* ---------------- utils ---------------- */

function key(s) {
  return `${s.rule_id}|${s.para}|${s.start_in_para}`;
}
function truncate(t, n) {
  t = (t || "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}
function escapeHtml(t) {
  return (t || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

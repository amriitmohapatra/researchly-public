/* Runs just after office.js on /word: see office-guard.js. */
(function () {
  var saved = window.__researchlyHistory;
  var h = window.history;
  if (!saved || !h) return;
  if (typeof h.pushState !== "function") h.pushState = saved.pushState;
  if (typeof h.replaceState !== "function") h.replaceState = saved.replaceState;
})();

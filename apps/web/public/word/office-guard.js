/*
 * Runs just before Microsoft's office.js on /word. In some Office hosts
 * office.js sets history.pushState and history.replaceState to null, which
 * breaks the page's router. Keep the originals; office-restore.js puts them
 * back right after office.js. Touches nothing else, and never any text.
 */
(function () {
  var h = window.history;
  if (h && !window.__researchlyHistory) {
    window.__researchlyHistory = { pushState: h.pushState, replaceState: h.replaceState };
  }
})();

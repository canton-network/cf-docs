// The Canton configuration reference shows every section twice, as HOCON and as a table, behind
// Mintlify tabs. Each Tabs group is independent, and a page has a dozen or more of them, so this
// keeps them in step: choosing a view in one section chooses it everywhere on the page, and the
// choice is remembered for the next page.
(function () {
  if (window.__CF_CANTON_CONFIG_VIEW_SYNC) {
    return;
  }
  window.__CF_CANTON_CONFIG_VIEW_SYNC = true;

  var STORAGE_KEY = "cf-canton-config-view";
  var VIEWS = { HOCON: true, Table: true };
  var PATH_MARKER = "/canton-config/";
  var syncing = false;

  function onReferencePage() {
    return window.location.pathname.indexOf(PATH_MARKER) !== -1;
  }

  function label(button) {
    return (button.textContent || "").trim();
  }

  function viewButtons() {
    var candidates = document.querySelectorAll('[role="tab"], button');
    return Array.prototype.filter.call(candidates, function (button) {
      return VIEWS[label(button)] === true;
    });
  }

  function isSelected(button) {
    return (
      button.getAttribute("aria-selected") === "true" ||
      button.getAttribute("data-state") === "active"
    );
  }

  function activate(view) {
    syncing = true;
    try {
      viewButtons().forEach(function (button) {
        if (label(button) === view && !isSelected(button)) {
          button.click();
        }
      });
    } finally {
      syncing = false;
    }
  }

  function remember(view) {
    try {
      window.localStorage.setItem(STORAGE_KEY, view);
    } catch (_) {
      // Storage can be unavailable; syncing within the page still works.
    }
  }

  function remembered() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (_) {
      return null;
    }
  }

  document.addEventListener(
    "click",
    function (event) {
      if (syncing || !onReferencePage() || !event.target || !event.target.closest) {
        return;
      }
      var button = event.target.closest('[role="tab"], button');
      if (!button) {
        return;
      }
      var view = label(button);
      if (VIEWS[view] !== true) {
        return;
      }
      remember(view);
      // Let the clicked group switch first, then bring the others along.
      window.setTimeout(function () {
        activate(view);
      }, 0);
    },
    true
  );

  var restoreTimer = null;
  function scheduleRestore() {
    if (!onReferencePage()) {
      return;
    }
    window.clearTimeout(restoreTimer);
    restoreTimer = window.setTimeout(function () {
      var view = remembered();
      if (view && VIEWS[view] === true) {
        activate(view);
      }
    }, 50);
  }

  scheduleRestore();
  // Mintlify navigates client-side, so watch for the content area being replaced.
  new MutationObserver(scheduleRestore).observe(document.body, { childList: true, subtree: true });
})();

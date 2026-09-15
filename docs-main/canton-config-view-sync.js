// The Canton configuration reference shows every section twice, as HOCON and as a table, behind
// Mintlify tabs. Each Tabs group is independent and a page has a dozen or more, so this adds one
// floating switch for the whole page, keeps every group in step with it (and with each other,
// should a reader use the inline tabs), and remembers the choice for the next page.
(function () {
  if (window.__CF_CANTON_CONFIG_VIEW_SYNC) {
    return;
  }
  window.__CF_CANTON_CONFIG_VIEW_SYNC = true;

  var STORAGE_KEY = "cf-canton-config-view";
  var VIEWS = ["HOCON", "Table"];
  var DEFAULT_VIEW = "HOCON";
  var PATH_MARKER = "/canton-config/";
  var TOGGLE_ID = "cf-canton-config-view-toggle";
  var syncing = false;

  var style = document.createElement("style");
  style.textContent =
    "#" + TOGGLE_ID + " {" +
    "  position: fixed; right: 1.25rem; bottom: 1.25rem; z-index: 60;" +
    "  display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.25rem;" +
    "  border-radius: 9999px; border: 1px solid rgba(128, 128, 128, 0.35);" +
    "  background: rgba(255, 255, 255, 0.92); backdrop-filter: blur(8px);" +
    "  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12); font-size: 0.8125rem; line-height: 1;" +
    "}" +
    "html.dark #" + TOGGLE_ID + " { background: rgba(24, 24, 27, 0.92); }" +
    "#" + TOGGLE_ID + " span { padding: 0 0.5rem; opacity: 0.6; }" +
    "#" + TOGGLE_ID + " button {" +
    "  border: 0; border-radius: 9999px; padding: 0.45rem 0.8rem; cursor: pointer;" +
    "  background: transparent; color: inherit; font: inherit;" +
    "}" +
    "#" + TOGGLE_ID + " button[aria-pressed=\"true\"] {" +
    "  background: rgba(99, 102, 241, 0.16); font-weight: 600;" +
    "}" +
    "@media (max-width: 640px) { #" + TOGGLE_ID + " { right: 0.75rem; bottom: 0.75rem; } }";
  document.head.appendChild(style);

  function onReferencePage() {
    return window.location.pathname.indexOf(PATH_MARKER) !== -1;
  }

  function label(button) {
    return (button.textContent || "").trim();
  }

  // The inline tab buttons only; the floating toggle's own buttons are excluded.
  function tabButtons() {
    var candidates = document.querySelectorAll('[role="tab"], button');
    return Array.prototype.filter.call(candidates, function (button) {
      return VIEWS.indexOf(label(button)) !== -1 && !button.hasAttribute("data-cf-view-toggle");
    });
  }

  function isSelected(button) {
    return (
      button.getAttribute("aria-selected") === "true" ||
      button.getAttribute("data-state") === "active"
    );
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
      var view = window.localStorage.getItem(STORAGE_KEY);
      return VIEWS.indexOf(view) !== -1 ? view : DEFAULT_VIEW;
    } catch (_) {
      return DEFAULT_VIEW;
    }
  }

  function paintToggle(view) {
    var toggle = document.getElementById(TOGGLE_ID);
    if (!toggle) {
      return;
    }
    Array.prototype.forEach.call(toggle.querySelectorAll("button"), function (button) {
      button.setAttribute("aria-pressed", label(button) === view ? "true" : "false");
    });
  }

  function activate(view) {
    syncing = true;
    try {
      tabButtons().forEach(function (button) {
        if (label(button) === view && !isSelected(button)) {
          button.click();
        }
      });
    } finally {
      syncing = false;
    }
    paintToggle(view);
  }

  function choose(view) {
    remember(view);
    activate(view);
  }

  function ensureToggle() {
    var existing = document.getElementById(TOGGLE_ID);
    if (!onReferencePage()) {
      if (existing) {
        existing.remove();
      }
      return;
    }
    if (existing || tabButtons().length === 0) {
      return;
    }
    var toggle = document.createElement("div");
    toggle.id = TOGGLE_ID;
    toggle.setAttribute("role", "group");
    toggle.setAttribute("aria-label", "Configuration view");
    var caption = document.createElement("span");
    caption.textContent = "View";
    toggle.appendChild(caption);
    VIEWS.forEach(function (view) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = view;
      button.setAttribute("data-cf-view-toggle", view);
      button.addEventListener("click", function () {
        choose(view);
      });
      toggle.appendChild(button);
    });
    document.body.appendChild(toggle);
    paintToggle(remembered());
  }

  // A reader who uses an inline tab still gets the whole page switched.
  document.addEventListener(
    "click",
    function (event) {
      if (syncing || !onReferencePage() || !event.target || !event.target.closest) {
        return;
      }
      var button = event.target.closest('[role="tab"], button');
      if (!button || button.hasAttribute("data-cf-view-toggle")) {
        return;
      }
      var view = label(button);
      if (VIEWS.indexOf(view) === -1) {
        return;
      }
      remember(view);
      window.setTimeout(function () {
        activate(view);
      }, 0);
    },
    true
  );

  var timer = null;
  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      ensureToggle();
      if (onReferencePage()) {
        activate(remembered());
      }
    }, 50);
  }

  schedule();
  // Mintlify navigates client-side, so watch for the content area being replaced.
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
})();

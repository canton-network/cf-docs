// The Canton configuration reference shows each section as a heading followed by Mintlify tabs
// (HOCON, Table) whose bodies run for hundreds of lines. Once the heading and the tab strip have
// scrolled away, a reader deep in a block no longer knows which section they are in or how to
// switch view. This keeps both in a bar pinned under the navbar while the reader is inside a
// section, and removes it once the section has been scrolled past. Only elements this script owns
// are added or moved; the page's own nodes are read and clicked, never restructured, so client-side
// navigation keeps working.
(function () {
  if (window.__CF_CANTON_CONFIG_SECTION_BAR) {
    return;
  }
  window.__CF_CANTON_CONFIG_SECTION_BAR = true;

  var PATH_MARKER = "/canton-config/";
  var BAR_ID = "cf-canton-config-section-bar";
  var VIEWS = ["HOCON", "Table"];
  var HEADINGS = "H2,H3,H4";

  var style = document.createElement("style");
  style.textContent =
    "#" + BAR_ID + " {" +
    "  position: fixed; z-index: 25; display: none; align-items: center; gap: 1rem;" +
    "  box-sizing: border-box; padding: 0.4rem 0 0.4rem;" +
    "  border-bottom: 1px solid rgba(128, 128, 128, 0.25);" +
    "  font-size: 0.8125rem; line-height: 1.25;" +
    "}" +
    "#" + BAR_ID + "[data-visible=\"true\"] { display: flex; }" +
    "#" + BAR_ID + " .cf-bar-title {" +
    "  flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" +
    "  font-weight: 600; color: inherit; text-decoration: none;" +
    "}" +
    "#" + BAR_ID + " .cf-bar-title code {" +
    "  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.8rem;" +
    "}" +
    "#" + BAR_ID + " .cf-bar-title .cf-bar-parent { opacity: 0.6; font-weight: 500; }" +
    "#" + BAR_ID + " .cf-bar-views { flex: 0 0 auto; display: inline-flex; gap: 1rem; }" +
    "#" + BAR_ID + " .cf-bar-views button {" +
    "  border: 0; border-bottom: 2px solid transparent; padding: 0.15rem 0; margin: 0;" +
    "  background: transparent; color: inherit; font: inherit; cursor: pointer; opacity: 0.7;" +
    "}" +
    "#" + BAR_ID + " .cf-bar-views button[aria-pressed=\"true\"] {" +
    "  opacity: 1; font-weight: 600; border-bottom-color: currentColor;" +
    "}";
  document.head.appendChild(style);

  function onReferencePage() {
    return window.location.pathname.indexOf(PATH_MARKER) !== -1;
  }

  function text(node) {
    // Mintlify prefixes headings with a zero-width anchor; drop it and any stray whitespace.
    return (node.textContent || "").replace(/[​\s]+/g, " ").trim();
  }

  function label(node) {
    return text(node);
  }

  // A section is a heading immediately followed by a Tabs group. For a fourth-level heading (a
  // `type = ...` variant) the enclosing third-level heading names the type it belongs to.
  function collectSections() {
    var content = document.querySelector(".mdx-content");
    if (!content) {
      return [];
    }
    var sections = [];
    var lastH3 = null;
    Array.prototype.forEach.call(content.children, function (node) {
      if (node.tagName === "H3") {
        lastH3 = node;
      }
      if (HEADINGS.indexOf(node.tagName) === -1) {
        return;
      }
      var next = node.nextElementSibling;
      if (!next || !next.classList.contains("tabs")) {
        return;
      }
      var tablist = next.querySelector('[role="tablist"]');
      if (!tablist) {
        return;
      }
      sections.push({
        heading: node,
        parent: node.tagName === "H4" ? lastH3 : null,
        tabs: next,
        tablist: tablist,
      });
    });
    return sections;
  }

  var sections = [];
  var current = null;

  function bar() {
    var existing = document.getElementById(BAR_ID);
    if (existing) {
      return existing;
    }
    var element = document.createElement("div");
    element.id = BAR_ID;
    // Mintlify's own background utilities keep the bar opaque in either theme.
    element.className = "bg-background-light dark:bg-background-dark";
    element.setAttribute("role", "region");
    element.setAttribute("aria-label", "Current configuration section");

    var title = document.createElement("a");
    title.className = "cf-bar-title";
    element.appendChild(title);

    var views = document.createElement("div");
    views.className = "cf-bar-views";
    views.setAttribute("role", "group");
    views.setAttribute("aria-label", "View");
    VIEWS.forEach(function (view) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = view;
      button.setAttribute("data-cf-view", view);
      button.addEventListener("click", function () {
        choose(view);
      });
      views.appendChild(button);
    });
    element.appendChild(views);
    document.body.appendChild(element);
    return element;
  }

  function tabFor(section, view) {
    var tabs = section.tablist.querySelectorAll('[role="tab"]');
    for (var i = 0; i < tabs.length; i++) {
      if (label(tabs[i]) === view) {
        return tabs[i];
      }
    }
    return null;
  }

  function selectedView(section) {
    var tabs = section.tablist.querySelectorAll('[role="tab"]');
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].getAttribute("aria-selected") === "true") {
        return label(tabs[i]);
      }
    }
    return VIEWS[0];
  }

  function choose(view) {
    if (!current) {
      return;
    }
    var tab = tabFor(current, view);
    if (tab && tab.getAttribute("aria-selected") !== "true") {
      // Switching view changes the section's height; keep the heading where the reader left it
      // rather than letting the page jump.
      var before = current.heading.getBoundingClientRect().top;
      tab.click();
      window.requestAnimationFrame(function () {
        var after = current.heading.getBoundingClientRect().top;
        if (after !== before) {
          window.scrollBy(0, after - before);
        }
        paint();
      });
    }
    paint();
  }

  function navbarBottom() {
    var navbar = document.getElementById("navbar");
    if (!navbar) {
      return 0;
    }
    var rect = navbar.getBoundingClientRect();
    return rect.bottom > 0 ? rect.bottom : 0;
  }

  function fillTitle(element, section) {
    var title = element.querySelector(".cf-bar-title");
    title.textContent = "";
    title.href = "#" + section.heading.id;
    if (section.parent) {
      var parent = document.createElement("span");
      parent.className = "cf-bar-parent";
      parent.textContent = text(section.parent) + " › ";
      title.appendChild(parent);
    }
    var code = document.createElement("code");
    code.textContent = text(section.heading);
    title.appendChild(code);
  }

  function paint() {
    var element = bar();
    if (!current) {
      element.setAttribute("data-visible", "false");
      return;
    }
    var view = selectedView(current);
    Array.prototype.forEach.call(element.querySelectorAll("button[data-cf-view]"), function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-cf-view") === view ? "true" : "false");
    });
  }

  function update() {
    if (!onReferencePage()) {
      var stale = document.getElementById(BAR_ID);
      if (stale) {
        stale.setAttribute("data-visible", "false");
      }
      current = null;
      return;
    }
    var content = document.querySelector(".mdx-content");
    var element = bar();
    var top = navbarBottom();
    var height = element.offsetHeight || 40;
    var found = null;
    for (var i = 0; i < sections.length; i++) {
      var section = sections[i];
      var headingTop = section.heading.getBoundingClientRect().top;
      var tabsBottom = section.tabs.getBoundingClientRect().bottom;
      // Inside a section: its heading has gone under the navbar and its tabs have not yet passed
      // the point where the bar would sit. The last such section is the innermost.
      if (headingTop < top && tabsBottom > top + height) {
        found = section;
      }
    }
    if (found !== current) {
      current = found;
      if (current) {
        fillTitle(element, current);
      }
    }
    if (!current) {
      element.setAttribute("data-visible", "false");
      return;
    }
    if (content) {
      var rect = content.getBoundingClientRect();
      element.style.left = rect.left + "px";
      element.style.width = rect.width + "px";
    }
    element.style.top = top + "px";
    element.setAttribute("data-visible", "true");
    paint();
  }

  var frame = null;
  function schedule() {
    if (frame !== null) {
      return;
    }
    frame = window.requestAnimationFrame(function () {
      frame = null;
      update();
    });
  }

  var rescanTimer = null;
  function rescan() {
    window.clearTimeout(rescanTimer);
    rescanTimer = window.setTimeout(function () {
      sections = onReferencePage() ? collectSections() : [];
      current = null;
      schedule();
    }, 50);
  }

  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
  // An inline tab click changes the selected view and the section's height.
  document.addEventListener("click", function () {
    window.setTimeout(schedule, 0);
  }, true);

  rescan();
  // Mintlify navigates client-side, so watch for the content area being replaced.
  new MutationObserver(rescan).observe(document.body, { childList: true, subtree: true });
})();

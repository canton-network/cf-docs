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
    "  box-sizing: border-box; padding: 0.55rem 0 0.55rem;" +
    "  border-bottom: 1px solid rgba(128, 128, 128, 0.25);" +
    "  font-size: 1rem; line-height: 1.3;" +
    "}" +
    "#" + BAR_ID + "[data-visible=\"true\"] { display: flex; }" +
    "#" + BAR_ID + " .cf-bar-title {" +
    "  flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" +
    "  font-weight: 600; color: inherit; text-decoration: none;" +
    "}" +
    "#" + BAR_ID + " .cf-bar-title code {" +
    "  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.95rem;" +
    "}" +
    "#" + BAR_ID + " .cf-bar-title .cf-bar-parent { opacity: 0.6; font-weight: 500; }" +
    "#" + BAR_ID + " .cf-bar-views { flex: 0 0 auto; display: inline-flex; gap: 1rem; }" +
    "#" + BAR_ID + " .cf-bar-views button {" +
    "  border: 0; border-bottom: 2px solid transparent; padding: 0.15rem 0; margin: 0;" +
    "  background: transparent; color: inherit; font: inherit; font-size: 1rem; cursor: pointer; opacity: 0.7;" +
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

  var KEY_LINE = /^\s*#?\s*([A-Za-z0-9_<>\-\[\].]+)\s*(=|\{)/;

  function documentTop(rect) {
    return rect.top + window.scrollY;
  }

  // The key named by a table row: its first cell, minus the indentation that marks nesting.
  // Rows that name a section rather than a key (bold, no code) yield nothing.
  function rowKey(row) {
    var cell = row.querySelector("td");
    if (!cell || !cell.querySelector("code")) {
      return null;
    }
    var key = text(cell.querySelector("code"));
    return key || null;
  }

  function lineKey(line) {
    var match = KEY_LINE.exec(line);
    return match ? match[1] : null;
  }

  // The lines of a code block with the vertical extent of each. A highlighter that wraps each
  // line in its own element gives exact boxes; otherwise lines are laid out from the block's
  // line height, which is uniform in a monospace block.
  function codeLines(pre) {
    var code = pre.querySelector("code") || pre;
    var wrapped = Array.prototype.filter.call(code.children, function (child) {
      return /\bline\b/.test(child.className || "");
    });
    if (wrapped.length > 1) {
      return wrapped.map(function (element) {
        var rect = element.getBoundingClientRect();
        return { text: element.textContent || "", top: documentTop(rect), bottom: documentTop(rect) + rect.height, element: element };
      });
    }
    var rect = code.getBoundingClientRect();
    var lines = (code.textContent || "").replace(/\n$/, "").split("\n");
    var height = rect.height / Math.max(lines.length, 1);
    var top = documentTop(rect);
    return lines.map(function (line, index) {
      return { text: line, top: top + index * height, bottom: top + (index + 1) * height, element: null };
    });
  }

  // Every key visible in the section's current view, as {key, top, bottom} in document
  // coordinates, in reading order.
  function keyPositions(section) {
    var positions = [];
    Array.prototype.forEach.call(section.tabs.querySelectorAll("pre"), function (pre) {
      if (pre.offsetParent === null) {
        return;
      }
      codeLines(pre).forEach(function (line) {
        var key = lineKey(line.text);
        if (key) {
          positions.push({ key: key, top: line.top, bottom: line.bottom, element: line.element });
        }
      });
    });
    Array.prototype.forEach.call(section.tabs.querySelectorAll("tbody tr"), function (row) {
      if (row.offsetParent === null) {
        return;
      }
      var key = rowKey(row);
      if (key) {
        var rect = row.getBoundingClientRect();
        positions.push({ key: key, top: documentTop(rect), bottom: documentTop(rect) + rect.height, element: row });
      }
    });
    return positions.sort(function (a, b) {
      return a.top - b.top;
    });
  }

  function extent(section) {
    var top = documentTop(section.heading.getBoundingClientRect());
    var bottom = documentTop(section.tabs.getBoundingClientRect()) + section.tabs.getBoundingClientRect().height;
    return { top: top, bottom: bottom, height: Math.max(bottom - top, 1) };
  }

  // Where the reader is in a section before a switch: the first key below the bar, and how far
  // down the section the bar sits as a fraction of its height. `readingLine` is a viewport
  // offset; everything measured is in document coordinates.
  function anchorIn(section, readingLine) {
    var span = extent(section);
    var reading = readingLine + window.scrollY;
    var positions = keyPositions(section);
    var key = null;
    for (var i = 0; i < positions.length; i++) {
      if (positions[i].bottom > reading) {
        key = positions[i].key;
        break;
      }
    }
    return { key: key, fraction: (reading - span.top) / span.height };
  }

  // After the switch, the place in the new view that corresponds to the anchor. The same key
  // name can recur within a section, so among matches the one at the nearest relative depth
  // wins. With no match, the same relative depth is kept. Returns what to keep under the bar:
  // an element when a key matched, else the fraction.
  function landingFor(section, anchor) {
    var span = extent(section);
    var best = null;
    if (anchor.key) {
      keyPositions(section).forEach(function (position) {
        if (position.key !== anchor.key) {
          return;
        }
        var distance = Math.abs((position.top - span.top) / span.height - anchor.fraction);
        if (best === null || distance < best.distance) {
          best = { position: position, distance: distance };
        }
      });
    }
    if (best !== null && best.position.element) {
      return { element: best.position.element, fraction: null };
    }
    if (best !== null) {
      return { element: null, fraction: (best.position.top - span.top) / span.height };
    }
    return { element: null, fraction: anchor.fraction };
  }

  // Scroll so the landing sits just under the bar, measured now. Whatever the landing, the
  // result stays inside the section, so the bar keeps showing the section the reader was in.
  function place(section, landing, readingLine, barHeight) {
    var span = extent(section);
    var top = landing.element
      ? documentTop(landing.element.getBoundingClientRect()) - 4
      : span.top + landing.fraction * span.height;
    var scrollTo = top - readingLine;
    var min = span.top - (readingLine - barHeight) + 1;
    var max = span.bottom - readingLine - 1;
    scrollTo = Math.max(min, Math.min(max, scrollTo));
    if (Math.abs(window.scrollY - scrollTo) > 1) {
      window.scrollTo(0, scrollTo);
    }
  }

  function choose(view) {
    if (!current) {
      return;
    }
    var section = current;
    var tab = tabFor(section, view);
    if (!tab || tab.getAttribute("aria-selected") === "true") {
      paint();
      return;
    }
    var element = bar();
    var barHeight = element.offsetHeight || 40;
    // The reading line is the bottom edge of the bar: what sits just beneath it is what the
    // reader was looking at.
    var readingLine = navbarBottom() + barHeight;
    var anchor = anchorIn(section, readingLine);
    tab.click();
    // The new view exists only after React has re-rendered, and other sections on the page
    // switch with it (Mintlify keeps tab groups in step), so wait for the new panel to be laid
    // out and then re-measure everything rather than assume.
    var started = Date.now();
    function settled() {
      if (tab.getAttribute("aria-selected") !== "true") {
        return false;
      }
      var wantsCode = view === VIEWS[0];
      var shown = section.tabs.querySelectorAll(wantsCode ? "pre" : "tbody tr");
      for (var i = 0; i < shown.length; i++) {
        if (shown[i].offsetParent !== null) {
          return true;
        }
      }
      return false;
    }
    // Mintlify switches every tab group on the page, so content above the section keeps changing
    // height for a few frames after this one has rendered, and the browser's own scroll anchoring
    // pulls against any single scroll. The landing is therefore held in place until the layout
    // has stopped moving, with anchoring switched off meanwhile.
    var root = document.documentElement;
    var previousAnchor = root.style.overflowAnchor;
    root.style.overflowAnchor = "none";
    var landing = null;
    var landedAt = 0;
    function land() {
      var now = Date.now();
      if (landing === null) {
        if (!settled() && now - started < 600) {
          window.requestAnimationFrame(land);
          return;
        }
        landing = landingFor(section, anchor);
        landedAt = now;
      }
      place(section, landing, readingLine, barHeight);
      if (now - landedAt < 500) {
        window.requestAnimationFrame(land);
        return;
      }
      root.style.overflowAnchor = previousAnchor;
      current = section;
      schedule();
    }
    window.requestAnimationFrame(land);
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

(function () {
  // Set to true when testing; enables console logging for analytics events.
  var DEBUG = false;

  if (window.__CF_GA_ANALYTICS_ADJUST) {
    return;
  }

  window.__CF_GA_ANALYTICS_ADJUST = true;

  var COPY_BUTTON_ARIA_PREFIX = "Copy the contents";
  var CONTENT_SELECTOR = ".mdx-content";
  var CODE_BLOCK_SELECTOR = "div.code-block";
  var CODE_COPY_EVENT = "code_block_copy_detailed";
  var NAV_EVENT = "navigation_detailed";
  var LOG_PREFIX = "[ga-analytics-adjust]";
  var HEADING_MAX_LEN = 60;
  var LINK_TEXT_MAX_LEN = 80;

  function debugLog() {
    if (!DEBUG) {
      return;
    }
    var args = Array.prototype.slice.call(arguments);
    args.unshift(LOG_PREFIX);
    console.log.apply(console, args);
  }

  function cleanText(value, maxLen) {
    var text = String(value || "")
      .replace(/\u200b/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (typeof maxLen === "number" && text.length > maxLen) {
      return text.slice(0, maxLen);
    }
    return text;
  }

  function sendEvent(eventName, eventParams) {
    if (typeof window.gtag === "function") {
      debugLog("firing gtag event", eventName, eventParams);
      window.gtag("event", eventName, eventParams);
      return;
    }

    // Fallback when gtag wrapper is not present but the data layer is.
    window.dataLayer = window.dataLayer || [];
    var payload = { event: eventName };
    for (var key in eventParams) {
      if (Object.prototype.hasOwnProperty.call(eventParams, key)) {
        payload[key] = eventParams[key];
      }
    }
    debugLog("pushing dataLayer event", payload);
    window.dataLayer.push(payload);
  }

  // --- Code block copy tracking -------------------------------------------

  function findCopyButton(target) {
    if (!(target instanceof Element)) {
      return null;
    }

    var button = target.closest("button[aria-label]");
    if (!button) {
      return null;
    }

    var aria = button.getAttribute("aria-label") || "";
    if (aria.indexOf(COPY_BUTTON_ARIA_PREFIX) === 0) {
      return button;
    }

    return null;
  }

  function findCodeBlock(copyButton) {
    return copyButton.closest(CODE_BLOCK_SELECTOR);
  }

  function contentArea() {
    return document.querySelector(CONTENT_SELECTOR);
  }

  function codeBlockIndex(codeBlock, area) {
    if (!area || !codeBlock) {
      return -1;
    }
    var blocks = area.querySelectorAll(CODE_BLOCK_SELECTOR);
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i] === codeBlock) {
        return i;
      }
    }
    return -1;
  }

  function codeBlockLanguage(codeBlock) {
    return codeBlock.getAttribute("language") || "";
  }

  // Walk previous siblings (then parents) for the nearest preceding H2/H3.
  function precedingHeadline(codeBlock, area) {
    var node = codeBlock;
    while (node && node !== area) {
      var sibling = node.previousElementSibling;
      while (sibling) {
        if (/^H[23]$/.test(sibling.tagName)) {
          return cleanText(sibling.innerText, HEADING_MAX_LEN);
        }
        sibling = sibling.previousElementSibling;
      }
      node = node.parentElement;
    }
    return "";
  }

  function trackCodeBlockCopy(event) {
    var copyButton = findCopyButton(event.target);
    if (!copyButton) {
      return false;
    }

    debugLog("code block copy button clicked");

    var area = contentArea();
    var codeBlock = findCodeBlock(copyButton);
    if (!codeBlock) {
      debugLog("no code-block ancestor found; skipping");
      return true;
    }

    var index = codeBlockIndex(codeBlock, area);
    sendEvent(CODE_COPY_EVENT, {
      code_block_id: index,
      code_block_language: codeBlockLanguage(codeBlock),
      code_block_last_headline: precedingHeadline(codeBlock, area),
    });
    return true;
  }

  // --- Navigation click tracking ------------------------------------------

  function isAssistantEntry(el) {
    if (!(el instanceof Element)) {
      return false;
    }
    // Navbar / mobile assistant toggles only (not per-code-block Ask buttons).
    return !!el.closest("#assistant-entry, #assistant-entry-mobile");
  }

  function findNavTarget(target) {
    if (!(target instanceof Element)) {
      return null;
    }

    var link = target.closest("a[href]");
    if (link) {
      return link;
    }

    var assistant = target.closest("#assistant-entry, #assistant-entry-mobile");
    if (assistant) {
      return assistant;
    }

    return null;
  }

  function navSourceFor(el) {
    // Assistant sits inside #navbar — check it before top_nav.
    if (isAssistantEntry(el)) {
      return "assistant";
    }
    if (el.closest("#sidebar, #navigation-items")) {
      return "sidebar";
    }
    if (el.closest("#navbar") || el.closest('[role="menu"]')) {
      return "top_nav";
    }
    if (
      el.closest(
        '#table-of-contents, #table-of-contents-content, nav[aria-label="On this page"]'
      )
    ) {
      // Extra source beyond the base enum: TOC was explicitly requested.
      return "toc";
    }
    if (el.closest('#pagination, nav[aria-label="Pagination"]')) {
      return "pagination";
    }
    if (
      el.closest(
        'nav[aria-label="Breadcrumb"], .breadcrumb-list, .x2mdx-ref-breadcrumbs'
      )
    ) {
      return "breadcrumb";
    }
    if (el.closest("#content, #content-area, .mdx-content")) {
      return "in_content";
    }
    return "other";
  }

  function sidebarGroupLabel(el) {
    var group = el.closest("ul.sidebar-group");
    if (!group) {
      return "";
    }

    var wrapper = group.parentElement;
    if (wrapper) {
      var header = wrapper.querySelector(
        ":scope > .sidebar-group-header .sidebar-title, :scope > .sidebar-group-header"
      );
      if (header) {
        return cleanText(header.innerText, LINK_TEXT_MAX_LEN);
      }
    }

    var prev = group.previousElementSibling;
    if (prev && prev.classList.contains("sidebar-group-header")) {
      return cleanText(prev.innerText, LINK_TEXT_MAX_LEN);
    }

    return "";
  }

  function pathFromHref(href) {
    if (!href) {
      return "";
    }
    if (
      href.indexOf("javascript:") === 0 ||
      href.indexOf("mailto:") === 0 ||
      href.indexOf("tel:") === 0
    ) {
      return "";
    }

    try {
      var url = new URL(href, window.location.href);
      return url.pathname + url.search + url.hash;
    } catch (err) {
      return href;
    }
  }

  function linkLabel(el) {
    var aria = el.getAttribute("aria-label");
    if (aria) {
      return cleanText(aria, LINK_TEXT_MAX_LEN);
    }
    return cleanText(el.innerText || el.textContent, LINK_TEXT_MAX_LEN);
  }

  function isNewTabClick(event) {
    if (event.metaKey || event.ctrlKey || event.button === 1) {
      return true;
    }
    var el = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (el && el.target === "_blank") {
      return true;
    }
    return false;
  }

  function trackNavigation(event) {
    // Ignore non-primary mouse buttons except middle-click (button === 1).
    if (typeof event.button === "number" && event.button !== 0 && event.button !== 1) {
      return false;
    }

    var navTarget = findNavTarget(event.target);
    if (!navTarget) {
      return false;
    }

    // Copy / feedback controls inside content should not count as navigation.
    if (findCopyButton(event.target)) {
      return false;
    }

    var source = navSourceFor(navTarget);
    var eventParams = {
      nav_source: source,
      nav_group: source === "sidebar" ? sidebarGroupLabel(navTarget) : "",
      from_path: window.location.pathname + window.location.search + window.location.hash,
      to_path:
        navTarget.tagName === "A"
          ? pathFromHref(navTarget.getAttribute("href"))
          : "",
      link_text: linkLabel(navTarget),
      new_tab: isNewTabClick(event) ? "yes" : "no",
    };

    debugLog("navigation click", eventParams);
    sendEvent(NAV_EVENT, eventParams);
    return true;
  }

  // Bubbling-phase delegated listeners: survive client-side route changes.
  document.addEventListener("click", function (event) {
    if (trackCodeBlockCopy(event)) {
      return;
    }
    trackNavigation(event);
  });

  // Middle-click opens a new tab and does not always fire a normal click.
  document.addEventListener("auxclick", function (event) {
    if (event.button !== 1) {
      return;
    }
    trackNavigation(event);
  });

  debugLog("analytics listeners registered");
})();

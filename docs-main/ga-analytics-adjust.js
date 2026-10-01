(function () {
  // Set to true when testing; enables console logging for copy events.
  var DEBUG = false;

  if (window.__CF_GA_ANALYTICS_ADJUST) {
    return;
  }

  window.__CF_GA_ANALYTICS_ADJUST = true;

  var COPY_BUTTON_ARIA_PREFIX = "Copy the contents";
  var CONTENT_SELECTOR = ".mdx-content";
  var CODE_BLOCK_SELECTOR = "div.code-block";
  var EVENT_NAME = "code_block_copy_detailed";
  var LOG_PREFIX = "[ga-analytics-adjust]";
  var HEADING_MAX_LEN = 60;

  function debugLog() {
    if (!DEBUG) {
      return;
    }
    var args = Array.prototype.slice.call(arguments);
    args.unshift(LOG_PREFIX);
    console.log.apply(console, args);
  }

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
          return sibling.innerText
            .replace(/\u200b/g, "")
            .trim()
            .slice(0, HEADING_MAX_LEN);
        }
        sibling = sibling.previousElementSibling;
      }
      node = node.parentElement;
    }
    return "";
  }

  function sendEvent(eventParams) {
    if (typeof window.gtag === "function") {
      debugLog("firing gtag event", EVENT_NAME, eventParams);
      window.gtag("event", EVENT_NAME, eventParams);
      return;
    }

    // Fallback when gtag wrapper is not present but the data layer is.
    window.dataLayer = window.dataLayer || [];
    var payload = { event: EVENT_NAME };
    for (var key in eventParams) {
      if (Object.prototype.hasOwnProperty.call(eventParams, key)) {
        payload[key] = eventParams[key];
      }
    }
    debugLog("pushing dataLayer event", payload);
    window.dataLayer.push(payload);
  }

  // Bubbling-phase delegated listener: survives client-side route changes.
  document.addEventListener("click", function (event) {
    var copyButton = findCopyButton(event.target);
    if (!copyButton) {
      return;
    }

    debugLog("code block copy button clicked");

    var area = contentArea();
    var codeBlock = findCodeBlock(copyButton);
    if (!codeBlock) {
      debugLog("no code-block ancestor found; skipping");
      return;
    }

    var index = codeBlockIndex(codeBlock, area);
    var eventParams = {
      code_block_id: index,
      code_block_language: codeBlockLanguage(codeBlock),
      code_block_last_headline: precedingHeadline(codeBlock, area),
    };

    sendEvent(eventParams);
  });

  debugLog("copy event listener registered");
})();

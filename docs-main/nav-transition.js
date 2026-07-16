(function () {
  if (window.__CF_NAV_TRANSITION) {
    return;
  }

  window.__CF_NAV_TRANSITION = true;

  var FADE_MS = 120;
  var SPINNER_FADE_IN_MS = 150;
  var TARGET_SELECTOR = "#content-area";
  var fadedOutFromClick = false;
  var spinnerElement = null;
  var contentCleanupTimer = null;

  var style = document.createElement("style");
  style.textContent =
    "#nav-loading-spinner {" +
    "  position: fixed;" +
    "  inset: 0;" +
    "  display: flex;" +
    "  align-items: center;" +
    "  justify-content: center;" +
    "  pointer-events: none;" +
    "  z-index: 5;" +
    "  opacity: 0;" +
    "  visibility: hidden;" +
    "  transition: opacity " +
    SPINNER_FADE_IN_MS +
    "ms ease-out, visibility 0s linear " +
    SPINNER_FADE_IN_MS +
    "ms;" +
    "}" +
    "#nav-loading-spinner.is-active {" +
    "  opacity: 1;" +
    "  visibility: visible;" +
    "  transition: opacity " +
    SPINNER_FADE_IN_MS +
    "ms ease-out, visibility 0s;" +
    "}" +
    ".nav-loading-spinner__ring {" +
    "  width: 1.25rem;" +
    "  height: 1.25rem;" +
    "  border: 2px solid rgba(115, 75, 226, 0.15);" +
    "  border-top-color: rgba(115, 75, 226, 0.55);" +
    "  border-radius: 50%;" +
    "  animation: nav-loading-spin 0.8s linear infinite;" +
    "}" +
    ":root.dark .nav-loading-spinner__ring," +
    "html.dark .nav-loading-spinner__ring {" +
    "  border-color: rgba(167, 133, 255, 0.15);" +
    "  border-top-color: rgba(167, 133, 255, 0.6);" +
    "}" +
    "@keyframes nav-loading-spin {" +
    "  to { transform: rotate(360deg); }" +
    "}";
  document.head.appendChild(style);

  function getContentArea() {
    return document.querySelector(TARGET_SELECTOR);
  }

  function installSpinner() {
    if (spinnerElement && document.contains(spinnerElement)) {
      return;
    }

    spinnerElement = document.createElement("div");
    spinnerElement.id = "nav-loading-spinner";
    spinnerElement.setAttribute("aria-hidden", "true");
    spinnerElement.innerHTML = '<div class="nav-loading-spinner__ring"></div>';
    document.body.appendChild(spinnerElement);
  }

  function showSpinner() {
    installSpinner();
    if (!spinnerElement) {
      return;
    }

    spinnerElement.style.removeProperty("transition");
    spinnerElement.classList.remove("is-active");
    forceReflow(spinnerElement);
    spinnerElement.classList.add("is-active");
  }

  function hideSpinner() {
    if (!spinnerElement) {
      return;
    }

    spinnerElement.style.transition = "none";
    spinnerElement.classList.remove("is-active");
    forceReflow(spinnerElement);
    spinnerElement.style.removeProperty("transition");
  }

  function getPagePath(urlString) {
    return new URL(urlString, window.location.origin).pathname;
  }

  function isPageNavigation(fromUrl, toUrl) {
    return getPagePath(fromUrl) !== getPagePath(toUrl);
  }

  function prepareTransition(element) {
    element.style.transition = "opacity " + FADE_MS + "ms ease-out";
    element.style.position = "relative";
    element.style.zIndex = "10";
  }

  function clearTransitionStyles(element) {
    element.style.removeProperty("opacity");
    element.style.removeProperty("transition");
    element.style.removeProperty("position");
    element.style.removeProperty("z-index");
  }

  function forceReflow(element) {
    void element.offsetWidth;
  }

  function fadeOut() {
    var contentArea = getContentArea();
    if (!contentArea) {
      return false;
    }

    showSpinner();
    prepareTransition(contentArea);
    contentArea.style.opacity = "1";
    forceReflow(contentArea);
    contentArea.style.opacity = "0";
    return true;
  }

  function fadeIn() {
    var contentArea = getContentArea();
    if (!contentArea) {
      hideSpinner();
      return false;
    }

    hideSpinner();
    prepareTransition(contentArea);
    contentArea.style.opacity = "0";
    forceReflow(contentArea);
    contentArea.style.opacity = "1";

    var finished = false;

    function finishTransition() {
      if (finished) {
        return;
      }
      finished = true;
      contentArea.removeEventListener("transitionend", onOpacityTransitionEnd);
      if (contentCleanupTimer) {
        window.clearTimeout(contentCleanupTimer);
        contentCleanupTimer = null;
      }
      clearTransitionStyles(contentArea);
    }

    function onOpacityTransitionEnd(event) {
      if (event.target !== contentArea || event.propertyName !== "opacity") {
        return;
      }
      finishTransition();
    }

    contentArea.addEventListener("transitionend", onOpacityTransitionEnd);
    contentCleanupTimer = window.setTimeout(finishTransition, FADE_MS + 50);
    return true;
  }

  function isInternalNavigationLink(link) {
    var href = link.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("mailto:")) {
      return null;
    }

    try {
      var url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) {
        return null;
      }
      return url;
    } catch (_error) {
      return null;
    }
  }

  function afterNavigationRender(callback) {
    requestAnimationFrame(function () {
      requestAnimationFrame(callback);
    });
  }

  function onPageReady() {
    hideSpinner();
    fadeIn();
  }

  installSpinner();

  document.addEventListener(
    "click",
    function (event) {
      var link = event.target.closest("a[href]");
      if (!link) {
        return;
      }

      var url = isInternalNavigationLink(link);
      if (!url || url.pathname === window.location.pathname) {
        return;
      }

      fadedOutFromClick = fadeOut();
    },
    true
  );

  if (typeof navigation !== "undefined") {
    navigation.addEventListener("navigate", function (event) {
      var fromUrl = navigation.currentEntry.url;
      var toUrl =
        event.destination && event.destination.url
          ? event.destination.url
          : window.location.href;

      if (!isPageNavigation(fromUrl, toUrl)) {
        fadedOutFromClick = false;
        return;
      }

      if (!fadedOutFromClick) {
        fadeOut();
      }

      fadedOutFromClick = false;
      afterNavigationRender(onPageReady);
    });
  }
})();

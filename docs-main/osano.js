(function (w, o, d) {
    w[o] =
        w[o] ||
        function () {
            w[o][d].push(arguments);
        };
    w[o][d] = w[o][d] || [];
})(window, 'Osano', 'data');

window.Osano('onAnalytics', consent => {
    loadGoogleTag();
});

(function loadOsano() {
    const osanoScript = document.createElement('script');
    osanoScript.src = 'https://cmp.osano.com/16A4BWTQ2aBjp3tNZ/54d97448-ff70-4b63-aaff-7dcf04da4e6c/osano.js';
    osanoScript.async = true;
    document.head.appendChild(osanoScript);

  })();

function loadGoogleTag() {
    const gtagScript = document.createElement('script');
    gtagScript.src = 'https://www.googletagmanager.com/gtag/js?id=G-F2G1L137JX';
    gtagScript.async = true;
  
    gtagScript.onload = function () {
        window.dataLayer = window.dataLayer || [];

        function gtag() {
        dataLayer.push(arguments);
        }

        window.gtag = gtag;

        gtag('js', new Date());
        gtag('config', 'G-F2G1L137JX');
    };
  
    document.head.appendChild(gtagScript);
}
(function () {
  const TARGETS = [
    "recommend_v2",
    "search_items",
  ];

  // ── Intercept fetch ──────────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input?.url || "";
    const response = await _fetch.apply(this, arguments);

    // Log mọi API call để debug
    if (url.includes("/api/")) {
      console.log("[SC] fetch:", url.substring(0, 100));
    }

    if (TARGETS.some((t) => url.includes(t))) {
      try {
        const data = await response.clone().json();
        console.log("[SC] MATCH:", url.substring(0, 80), "units:", data?.data?.units?.length);
        window.postMessage(
          { source: "SHOPEE_CRAWLER", type: "API_DATA", url, data },
          "*"
        );
      } catch (e) {
        console.log("[SC] parse error:", e.message);
      }
    }

    return response;
  };

  // ── Intercept XMLHttpRequest ─────────────────────────────────────────────────
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url) {
    this._scraperUrl = url;
    return _open.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function () {
    const url = this._scraperUrl || "";
    if (TARGETS.some((t) => url.includes(t))) {
      this.addEventListener("load", function () {
        try {
          const data = JSON.parse(this.responseText);
          window.postMessage(
            { source: "SHOPEE_CRAWLER", type: "API_DATA", url, data },
            "*"
          );
        } catch (_) {}
      });
    }
    return _send.apply(this, arguments);
  };

  console.log("[Shopee Crawler] Interceptor ready.");
})();

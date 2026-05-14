// Relay messages from page context (MAIN world) → background service worker
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data?.source !== "SHOPEE_CRAWLER") return;
  chrome.runtime.sendMessage(event.data).catch(() => {});
});

// ─── Fast Mode ────────────────────────────────────────────────────────────────
// Shopee fires the product API on page load — no scrolling needed to capture
// data. We just wait 2.5s for the response, then immediately navigate next.

let fastTimer  = null;

function startFastMode() {
  if (fastTimer) return;
  fastTimer = setTimeout(() => {
    fastTimer = null;
    if (!goToNextPage()) {
      chrome.runtime.sendMessage({ type: "ALL_PAGES_DONE" }).catch(() => {});
    }
  }, 2500);
}

function stopFastMode() {
  if (fastTimer) { clearTimeout(fastTimer); fastTimer = null; }
}

// ─── Scroll Mode (fallback) ───────────────────────────────────────────────────

let scrollTimer  = null;
let stalledCount = 0;

function startScrollMode() {
  if (scrollTimer) return;
  stalledCount = 0;
  scrollTimer  = setTimeout(scrollStep, 1500);
}

function stopScrollMode() {
  if (scrollTimer) { clearTimeout(scrollTimer); scrollTimer = null; }
}

function scrollStep() {
  scrollTimer = null;
  const atBottom = window.scrollY + window.innerHeight >= document.body.scrollHeight - 300;

  if (atBottom) {
    stalledCount++;
    if (stalledCount >= 3) {
      if (goToNextPage()) return;
      chrome.runtime.sendMessage({ type: "ALL_PAGES_DONE" }).catch(() => {});
      return;
    }
  } else {
    stalledCount = 0;
  }

  const dist  = 700 + Math.floor(Math.random() * 500);
  const delay = 1200 + Math.floor(Math.random() * 1300);
  window.scrollBy({ top: dist, behavior: "smooth" });
  scrollTimer = setTimeout(scrollStep, delay);
}

// ─── Shared ───────────────────────────────────────────────────────────────────

function goToNextPage() {
  const nextBtn = document.querySelector(
    "a.shopee-icon-button--right:not([aria-disabled='true'])"
  );
  if (!nextBtn || !nextBtn.href) return false;
  window.scrollTo(0, 0);
  nextBtn.click();
  return true;
}

// ─── Listen for commands from background ──────────────────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "START_FAST")   startFastMode();
  if (msg.type === "START_SCROLL") startScrollMode();
  if (msg.type === "STOP_SCROLL")  { stopFastMode(); stopScrollMode(); }
});

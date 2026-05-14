const SERVER = "http://localhost:7979";

let collecting      = false;
let crawlMode       = "fast";
let crawlTabId      = null;
let categories      = [];
let catIdx          = -1;
let currentCategory = null;
let lastExported    = 0;
let count           = 0;
const seenLinks     = new Set();

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "API_DATA") {
    handleApiData(msg.data);
    return false;
  }

  if (msg.type === "START") {
    // Reset everything for a fresh crawl
    collecting   = true;
    crawlMode    = msg.crawlMode || "fast";
    lastExported = 0;
    count        = 0;
    seenLinks.clear();

    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      crawlTabId = tabs[0]?.id;
      await pingServer("start");
      await loadCategoriesAndBegin();
    });

    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "ALL_PAGES_DONE") {
    // Current category finished — move to next (or export if all done)
    advanceCategory();
    return false;
  }

  if (msg.type === "STOP") {
    const wasCollecting = collecting;
    collecting = false;
    if (crawlTabId != null) {
      chrome.tabs.sendMessage(crawlTabId, { type: "STOP_SCROLL" }).catch(() => {});
    }
    // Skip export if finishAll() already exported (lastExported set, count > 0)
    if (!wasCollecting && lastExported > 0) {
      sendResponse({ count, exported: lastExported });
      return false;
    }
    pingServer("export").then((res) => {
      lastExported = res?.filtered ?? 0;
      sendResponse({ count, exported: lastExported });
    });
    return true;
  }

  if (msg.type === "GET_STATUS") {
    sendResponse({
      collecting,
      count,
      lastExported,
      catIdx,
      totalCats: categories.length,
      catName:   currentCategory?.name ?? "",
    });
    return false;
  }
});

// ─── Category orchestration ───────────────────────────────────────────────────

async function loadCategoriesAndBegin() {
  try {
    const res = await fetch(`${SERVER}/categories`);
    if (res.ok) categories = await res.json();
    else        categories = [];
  } catch (_) {
    categories = [];
  }
  catIdx = -1;
  advanceCategory();
}

function advanceCategory() {
  catIdx++;
  if (catIdx >= categories.length) {
    finishAll();
    return;
  }
  currentCategory = categories[catIdx];
  updateBadge(count);
  if (crawlTabId != null) {
    chrome.tabs.update(crawlTabId, { url: currentCategory.url });
    // chrome.tabs.onUpdated fires START_FAST/START_SCROLL once page loads
  }
}

function finishAll() {
  collecting = false;
  pingServer("export").then((res) => {
    lastExported = res?.filtered ?? 0;
    updateBadge(count);
  });
}

// ─── Parse & buffer ───────────────────────────────────────────────────────────

function handleApiData(data) {
  const items    = parseItems(data);
  const newItems = [];

  for (const item of items) {
    if (seenLinks.has(item.product_link)) continue;
    item.category = currentCategory?.name ?? "";
    seenLinks.add(item.product_link);
    newItems.push(item);
    count++;
  }

  updateBadge(count);

  if (collecting && newItems.length > 0) {
    sendToServer(newItems);
  }
}

// ─── Parsers ─────────────────────────────────────────────────────────────────

function parseItems(data) {
  if (data?.data?.units) return parseRecommendV2(data.data.units);
  if (data?.items)       return parseSearchItems(data.items);
  return [];
}

function parseRecommendV2(units) {
  const results = [];
  for (const unit of units) {
    const asset    = unit?.item?.item_card_displayed_asset;
    const itemData = unit?.item?.item_data;
    if (!asset?.name || !itemData?.itemid || !itemData?.shopid) continue;

    const priceRaw = itemData.item_card_display_price?.price ?? 0;
    const priceVnd = Math.round(priceRaw / 100000);
    const flag     = asset.seller_flag?.name ?? "";
    const shopType = flag === "MALL"      ? "mall"
                   : flag === "PREFERRED" ? "preferred"
                   : "normal";

    results.push({
      name:         asset.name,
      price:        priceVnd > 0 ? `${priceVnd.toLocaleString("vi-VN")} ₫` : "",
      sold_count:   asset.sold_count?.text ?? "",
      rating:       itemData.item_rating?.rating_star
                      ? itemData.item_rating.rating_star.toFixed(1)
                      : "",
      shop_type:    shopType,
      product_link: `https://shopee.vn/product/${itemData.shopid}/${itemData.itemid}`,
    });
  }
  return results;
}

function parseSearchItems(items) {
  const results = [];
  for (const entry of items) {
    const item = entry?.item_basic ?? entry;
    if (!item?.name || !item?.itemid || !item?.shopid) continue;

    const priceVnd = Math.round((item.price_min ?? item.price ?? 0) / 100000);
    const shopType = item.is_official_shop         ? "mall"
                   : item.is_preferred_plus_seller  ? "preferred"
                   : "normal";

    results.push({
      name:         item.name,
      price:        priceVnd > 0 ? `${priceVnd.toLocaleString("vi-VN")} ₫` : "",
      sold_count:   String(item.historical_sold ?? ""),
      rating:       item.item_rating?.rating_star
                      ? item.item_rating.rating_star.toFixed(1)
                      : "",
      shop_type:    shopType,
      product_link: `https://shopee.vn/product/${item.shopid}/${item.itemid}`,
    });
  }
  return results;
}

// ─── Server ───────────────────────────────────────────────────────────────────

function sendToServer(items) {
  if (!items.length) return;
  fetch(`${SERVER}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  }).catch(() => {});
}

async function pingServer(action) {
  try {
    const res = await fetch(`${SERVER}/${action}`, { method: "POST" });
    return res.ok ? res.json() : null;
  } catch (_) {
    return null;
  }
}

// ─── Badge ────────────────────────────────────────────────────────────────────

function updateBadge(n) {
  const label = n >= 1000 ? `${Math.floor(n / 1000)}k` : String(n);
  chrome.action.setBadgeText({ text: label });
  chrome.action.setBadgeBackgroundColor({ color: "#EE4D2D" });
}

// ─── Auto-restart after page navigation ──────────────────────────────────────
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!collecting) return;
  if (changeInfo.status !== "complete") return;
  if (!tab.url?.includes("shopee.vn")) return;

  const delay = crawlMode === "fast" ? 500 : 2000;
  const type  = crawlMode === "fast" ? "START_FAST" : "START_SCROLL";
  setTimeout(() => {
    chrome.tabs.sendMessage(tabId, { type }).catch(() => {});
  }, delay);
});

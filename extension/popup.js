const countEl    = document.getElementById("count");
const progressEl = document.getElementById("progress");
const resultEl   = document.getElementById("result");
const hintEl     = document.getElementById("hint");
const badgeEl    = document.getElementById("server-badge");
const btnStart   = document.getElementById("btn-start");
const btnStop    = document.getElementById("btn-stop");

let pollTimer    = null;
let selectedMode = "fast";

// ─── Mode selector ────────────────────────────────────────────────────────────

function setMode(mode) {
  selectedMode = mode;
  document.getElementById("btn-fast").classList.toggle("active", mode === "fast");
  document.getElementById("btn-scroll").classList.toggle("active", mode === "scroll");
}

// ─── Server health ────────────────────────────────────────────────────────────

async function checkServer() {
  try {
    const res = await fetch("http://localhost:7979/status");
    if (res.ok) {
      badgeEl.textContent = "✓ Server đang chạy";
      badgeEl.className   = "server-badge ok";
      return true;
    }
  } catch (_) {}
  badgeEl.textContent = "⚠ Chạy: python server.py";
  badgeEl.className   = "server-badge err";
  return false;
}

// ─── State sync ───────────────────────────────────────────────────────────────

function refreshState() {
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (res) => {
    if (chrome.runtime.lastError || !res) return;

    countEl.textContent = res.count;

    if (res.collecting) {
      setCollecting(res);
    } else {
      setStopped(res);
    }
  });
}

function setCollecting(res) {
  btnStart.style.display = "none";
  btnStop.style.display  = "block";
  resultEl.textContent   = "";

  if (res.totalCats > 0) {
    progressEl.textContent = `Danh mục ${res.catIdx + 1}/${res.totalCats}: ${res.catName}`;
    hintEl.textContent     = selectedMode === "fast"
      ? "⚡ Đang chạy nhanh... Không đóng tab Shopee."
      : "🖱 Đang scroll... Không đóng tab Shopee.";
  } else {
    progressEl.textContent = "";
    hintEl.textContent     = "Đang tải danh mục...";
  }
}

function setStopped(res) {
  btnStart.style.display = "block";
  btnStop.style.display  = "none";
  progressEl.textContent = "";
  hintEl.textContent     = "Nhấn Bắt đầu — extension tự động crawl\ntất cả danh mục trong config.json.";

  if (res.lastExported > 0) {
    resultEl.textContent = `✓ Xuất ${res.lastExported}/${res.count} sản phẩm (sau lọc).`;
  } else if (res.count === 0) {
    resultEl.textContent = "";
  }
}

// ─── Buttons ──────────────────────────────────────────────────────────────────

btnStart.addEventListener("click", async () => {
  const serverOk = await checkServer();
  if (!serverOk) return;

  resultEl.textContent   = "";
  progressEl.textContent = "Đang khởi động...";

  chrome.runtime.sendMessage({ type: "START", crawlMode: selectedMode }, () => {
    countEl.textContent = "0";
    setCollecting({ totalCats: 0, catIdx: -1, catName: "" });
    startPolling();
  });
});

btnStop.addEventListener("click", () => {
  btnStop.disabled    = true;
  btnStop.textContent = "Đang export...";
  stopPolling();

  chrome.runtime.sendMessage({ type: "STOP" }, (res) => {
    btnStop.disabled    = false;
    btnStop.textContent = "⏹ Dừng & Export";
    const total    = res?.count    ?? 0;
    const exported = res?.exported ?? 0;
    resultEl.textContent = `✓ Xuất ${exported}/${total} sản phẩm (sau lọc).`;
    setStopped({ count: total, lastExported: exported });
  });
});

// ─── Polling ──────────────────────────────────────────────────────────────────

function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    refreshState();
    // stop polling automatically once crawl finishes
  }, 800);
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

checkServer();
refreshState();

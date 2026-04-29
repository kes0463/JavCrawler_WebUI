function formatClock(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function el(id) {
  return document.getElementById(id);
}

function toAbsUrl(maybeRelativeUrl) {
  try {
    if (!maybeRelativeUrl) return "";
    return new URL(String(maybeRelativeUrl), window.location.href).href;
  } catch {
    return String(maybeRelativeUrl || "");
  }
}

function uniqSorted(values) {
  const set = new Set();
  for (const v of values) {
    const s = (v ?? "").toString().trim();
    if (!s) continue;
    set.add(s);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

async function loadDatabase() {
  if (window.JAV_DATABASE && typeof window.JAV_DATABASE === "object") {
    return window.JAV_DATABASE;
  }

  // Fallback: fetch JSON (requires local server in many browsers)
  const res = await fetch("./web_database.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`web_database.json 로딩 실패: ${res.status}`);
  return await res.json();
}

async function loadMaster() {
  // CORS-safe: data/derived/master_db.js가 있으면 전역 변수로 로드됨
  if (Array.isArray(window.MASTER_DB)) {
    return window.MASTER_DB;
  }
  return null;
}

function flattenCards(db) {
  const zones = Array.isArray(db?.zones) ? db.zones : [];
  const cards = [];

  for (const z of zones) {
    const zoneLabel = z?.zone || "UNKNOWN";
    const zStart = Number(z?.start ?? 0);
    const zEnd = Number(z?.end ?? 0);

    const sub = Array.isArray(z?.sub_chapters) ? z.sub_chapters : [];
    for (const sc of sub) {
      const t = Number(sc?.start_t ?? zStart);
      const position = sc?.position ?? "unclear";
      const action = sc?.action ?? "unknown";
      const intensity = sc?.intensity ?? "?";
      const description = sc?.description ?? "";

      // 대표 스냅샷 찾기: 해당 zone 범위 내에서 t가 가장 가까운 vlm 스냅샷
      let image = null;
      const snaps = Array.isArray(z?.vlm_snapshots) ? z.vlm_snapshots : [];
      if (snaps.length) {
        let best = null;
        let bestDist = Infinity;
        for (const s of snaps) {
          if (!s || s.error) continue;
          const st = Number(s.t ?? NaN);
          if (!Number.isFinite(st)) continue;
          const d = Math.abs(st - t);
          if (d < bestDist) {
            bestDist = d;
            best = s;
          }
        }
        if (best && typeof best.screenshot === "string") {
          image = best.screenshot;
        }
      }

      cards.push({
        t,
        zoneLabel,
        zoneStart: zStart,
        zoneEnd: zEnd,
        position,
        action,
        intensity,
        description,
        image,
      });
    }
  }

  cards.sort((a, b) => a.t - b.t);
  return cards;
}

function setStatus(text) {
  el("statusText").textContent = text;
}

function render(cards) {
  const timeline = el("timeline");
  const emptyState = el("emptyState");
  timeline.innerHTML = "";

  if (!cards.length) {
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  for (const c of cards) {
    const card = document.createElement("button");
    card.type = "button";
    card.className =
      "card rounded-xl overflow-hidden text-left w-full focus:outline-none focus:ring-2 focus:ring-netflix-red/40";
    card.dataset.t = String(c.t);

    const img = c.image
      ? `<img src="${c.image}" class="w-full h-32 object-cover bg-black" alt="shot" />`
      : `<div class="w-full h-32 bg-black/60 flex items-center justify-center text-netflix-muted text-xs">NO SHOT</div>`;

    card.innerHTML = `
      ${img}
      <div class="p-3">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-semibold truncate">${c.position} · ${c.action}</div>
          <div class="text-xs font-mono text-netflix-muted">${formatClock(c.t)}</div>
        </div>
        <div class="mt-2 flex items-center gap-2 flex-wrap">
          <span class="badge text-xs px-2 py-0.5 rounded-full text-netflix-muted">LOC: ${c.zoneLabel}</span>
          <span class="badge text-xs px-2 py-0.5 rounded-full text-netflix-muted">INT: ${c.intensity}</span>
        </div>
        <div class="mt-2 text-xs text-netflix-muted line-clamp-2">${c.description || ""}</div>
      </div>
    `;

    timeline.appendChild(card);
  }
}

function wireInteractionsForMaster(masterEntries, cards) {
  const video = el("video");
  const currentTimeText = el("currentTimeText");
  const currentZoneText = el("currentZoneText");
  const currentChapterText = el("currentChapterText");

  el("countsText").textContent = `${cards.length} cards`;

  // click-to-seek
  el("timeline").addEventListener("click", (e) => {
    const btn = e.target?.closest?.("button[data-t]");
    if (!btn) return;
    const t = Number(btn.dataset.t);
    if (!Number.isFinite(t)) return;

    const idx = Number(btn.dataset.idx);
    const c = cards[idx];
    if (!c) return;

    const newSrc = c.videoSrc;
    if (typeof newSrc === "string" && newSrc.trim() && video.src !== newSrc.trim()) {
      video.src = newSrc.trim();
    }

    const seekTo = Math.max(0, c.t);
    const doSeek = () => {
      video.currentTime = seekTo;
      video.play().catch(() => {});
    };
    if (video.readyState >= 1) {
      doSeek();
    } else {
      video.addEventListener("loadedmetadata", doSeek, { once: true });
    }
  });

  function updateActive() {
    const t = video.currentTime || 0;
    currentTimeText.textContent = formatClock(t);

    // active card: 현재 video.src와 동일한 카드 중 시간 가장 근접
    let bestIdx = -1;
    let bestDist = Infinity;
    for (let i = 0; i < cards.length; i++) {
      if (cards[i].videoSrc && video.src && cards[i].videoSrc !== video.src) continue;
      const d = Math.abs(cards[i].t - t);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }

    const nodes = document.querySelectorAll("#timeline button[data-t]");
    nodes.forEach((n) => n.classList.remove("active"));
    if (bestIdx >= 0) {
      const active = nodes[bestIdx];
      if (active) active.classList.add("active");
      const c = cards[bestIdx];
      currentZoneText.textContent = `${c.zoneLabel}`;
      currentChapterText.textContent = `${c.position} · ${c.action} (${formatClock(c.t)})`;
    } else {
      currentZoneText.textContent = "-";
      currentChapterText.textContent = "-";
    }
  }

  video.addEventListener("timeupdate", updateActive);
  video.addEventListener("loadedmetadata", updateActive);
  updateActive();
}

(async function main() {
  try {
    setStatus("데이터 로딩 중...");

    const master = await loadMaster();
    const masterEntries = Array.isArray(master) ? master : null;
    if (masterEntries && masterEntries.length) {
      // MASTER MODE
      const cardsAll = masterEntries.map((e, idx) => ({
        idx,
        t: Number(e?.scene?.t ?? 0),
        zoneLabel: e?.scene?.zone ?? "UNKNOWN",
        position: e?.scene?.position ?? "unclear",
        action: e?.scene?.action ?? "unknown",
        intensity: e?.scene?.intensity ?? "?",
        description: e?.scene?.description ?? "",
        image: typeof e?.thumb === "string" ? e.thumb : null,
        videoSrc: typeof e?.video?.src === "string" ? e.video.src : "",
        absVideoSrc: typeof e?.video?.src === "string" ? toAbsUrl(e.video.src) : "",
        _text: typeof e?.text === "string" ? e.text : "",
      }));

      // Filters
      const locations = uniqSorted(cardsAll.map((c) => c.zoneLabel));
      const positions = uniqSorted(cardsAll.map((c) => c.position));
      const intensities = uniqSorted(cardsAll.map((c) => c.intensity));

      // Fuse
      const fuse = new Fuse(cardsAll, {
        includeScore: true,
        threshold: 0.35,
        ignoreLocation: true,
        keys: ["_text", "description", "action", "position", "zoneLabel", "intensity"],
      });

      const searchInput = el("searchInput");
      const clearBtn = el("clearSearchBtn");
      const locSel = el("filterLocation");
      const posSel = el("filterPosition");
      const intSel = el("filterIntensity");

      // fill dropdowns
      const fill = (selectEl, items) => {
        if (!selectEl) return;
        const first = selectEl.querySelector("option[value='']");
        selectEl.innerHTML = "";
        if (first) selectEl.appendChild(first);
        for (const v of items) {
          const opt = document.createElement("option");
          opt.value = v;
          opt.textContent = v;
          selectEl.appendChild(opt);
        }
      };
      fill(locSel, locations);
      fill(posSel, positions);
      fill(intSel, intensities);

      function applyFiltersAndRender() {
        const q = (searchInput?.value ?? "").trim();
        const location = (locSel?.value ?? "").trim();
        const position = (posSel?.value ?? "").trim();
        const intensity = (intSel?.value ?? "").trim();

        let base = cardsAll;
        if (q) {
          base = fuse.search(q).map((r) => r.item);
        }

        const filtered = base.filter((c) => {
          if (location && c.zoneLabel !== location) return false;
          if (position && c.position !== position) return false;
          if (intensity && c.intensity !== intensity) return false;
          return true;
        });

        // re-index for DOM mapping
        const cards = filtered
          .slice()
          .sort((a, b) => {
            const av = (a.videoSrc || "").localeCompare(b.videoSrc || "");
            if (av !== 0) return av;
            return (a.t || 0) - (b.t || 0);
          })
          .map((c, i) => ({ ...c, _renderIndex: i }));

        // render
        const timeline = el("timeline");
        const emptyState = el("emptyState");
        timeline.innerHTML = "";
        if (!cards.length) {
          emptyState.classList.remove("hidden");
        } else {
          emptyState.classList.add("hidden");
        }

        for (const c of cards) {
          const card = document.createElement("button");
          card.type = "button";
          card.className =
            "card rounded-xl overflow-hidden text-left w-full focus:outline-none focus:ring-2 focus:ring-netflix-red/40";
          card.dataset.t = String(c.t);
          card.dataset.idx = String(c._renderIndex);

          const img = c.image
            ? `<img src="${c.image}" class="w-full h-32 object-cover bg-black" alt="shot" />`
            : `<div class="w-full h-32 bg-black/60 flex items-center justify-center text-netflix-muted text-xs">NO SHOT</div>`;

          card.innerHTML = `
            ${img}
            <div class="p-3">
              <div class="flex items-center justify-between gap-2">
                <div class="text-sm font-semibold truncate">${c.position} · ${c.action}</div>
                <div class="text-xs font-mono text-netflix-muted">${formatClock(c.t)}</div>
              </div>
              <div class="mt-2 flex items-center gap-2 flex-wrap">
                <span class="badge text-xs px-2 py-0.5 rounded-full text-netflix-muted">LOC: ${c.zoneLabel}</span>
                <span class="badge text-xs px-2 py-0.5 rounded-full text-netflix-muted">INT: ${c.intensity}</span>
              </div>
              <div class="mt-2 text-xs text-netflix-muted line-clamp-2">${c.description || ""}</div>
            </div>
          `;
          timeline.appendChild(card);
        }

        el("countsText").textContent = `${cards.length} cards`;

        // interactions need current rendered cards array
        wireMasterRuntime(cards);
      }

      // runtime wiring: re-bind active update to current cards list
      const video = el("video");
      const currentTimeText = el("currentTimeText");
      const currentZoneText = el("currentZoneText");
      const currentChapterText = el("currentChapterText");
      let activeCards = [];

      // click handler once
      el("timeline").addEventListener("click", (e) => {
        const btn = e.target?.closest?.("button[data-t]");
        if (!btn) return;
        const idx = Number(btn.dataset.idx);
        const c = activeCards[idx];
        if (!c) return;

        const newSrc = c.videoSrc;
        if (typeof newSrc === "string" && newSrc.trim()) {
          const absNew = toAbsUrl(newSrc.trim());
          if (toAbsUrl(video.getAttribute("src") || "") !== absNew) {
            video.src = newSrc.trim(); // 브라우저가 절대 URL로 승격
          }
        }

        const seekTo = Math.max(0, c.t);
        const doSeek = () => {
          video.currentTime = seekTo;
          video.play().catch(() => {});
        };
        if (video.readyState >= 1) doSeek();
        else video.addEventListener("loadedmetadata", doSeek, { once: true });
      });

      function updateActive() {
        const t = video.currentTime || 0;
        currentTimeText.textContent = formatClock(t);

        const absCurrent = toAbsUrl(video.currentSrc || video.src || video.getAttribute("src") || "");
        let bestIdx = -1;
        let bestDist = Infinity;
        for (let i = 0; i < activeCards.length; i++) {
          if (activeCards[i].absVideoSrc && absCurrent && activeCards[i].absVideoSrc !== absCurrent) continue;
          const d = Math.abs(activeCards[i].t - t);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = i;
          }
        }

        const nodes = document.querySelectorAll("#timeline button[data-t]");
        nodes.forEach((n) => n.classList.remove("active"));
        if (bestIdx >= 0) {
          const active = nodes[bestIdx];
          if (active) active.classList.add("active");
          const c = activeCards[bestIdx];
          currentZoneText.textContent = `${c.zoneLabel}`;
          currentChapterText.textContent = `${c.position} · ${c.action} (${formatClock(c.t)})`;
        } else {
          currentZoneText.textContent = "-";
          currentChapterText.textContent = "-";
        }
      }

      function wireMasterRuntime(cards) {
        activeCards = cards;
        updateActive();
      }

      video.addEventListener("timeupdate", updateActive);
      video.addEventListener("loadedmetadata", updateActive);

      // UI wiring
      const debounce = (fn, ms) => {
        let t = null;
        return () => {
          if (t) clearTimeout(t);
          t = setTimeout(fn, ms);
        };
      };
      const applyDebounced = debounce(applyFiltersAndRender, 80);
      searchInput?.addEventListener("input", applyDebounced);
      locSel?.addEventListener("change", applyFiltersAndRender);
      posSel?.addEventListener("change", applyFiltersAndRender);
      intSel?.addEventListener("change", applyFiltersAndRender);
      clearBtn?.addEventListener("click", () => {
        if (searchInput) searchInput.value = "";
        if (locSel) locSel.value = "";
        if (posSel) posSel.value = "";
        if (intSel) intSel.value = "";
        applyFiltersAndRender();
      });

      applyFiltersAndRender();
      setStatus(`MASTER_DB 로딩 완료 (${masterEntries.length} scenes)`);
      return;
    }

    // FALLBACK: SINGLE VIDEO MODE (기존 동작)
    const db = await loadDatabase();
    const cards = flattenCards(db);
    // 기존 카드 구조에 video src 연결
    const src = db?.video?.src;
    const video = el("video");
    if (typeof src === "string" && src.trim()) video.src = src.trim();

    const dur = db?.video?.duration;
    const fps = db?.video?.fps;
    const metaParts = [];
    if (typeof dur === "number" && Number.isFinite(dur) && dur > 0) metaParts.push(`Dur ${formatClock(dur)}`);
    if (typeof fps === "number" && Number.isFinite(fps) && fps > 0) metaParts.push(`FPS ${fps.toFixed(2)}`);
    el("videoMeta").textContent = metaParts.join(" · ");

    // render fallback
    render(cards);

    // simple interactions (single)
    el("countsText").textContent = `${cards.length} cards`;
    el("timeline").addEventListener("click", (e) => {
      const btn = e.target?.closest?.("button[data-t]");
      if (!btn) return;
      const t = Number(btn.dataset.t);
      if (!Number.isFinite(t)) return;
      video.currentTime = Math.max(0, t);
      video.play().catch(() => {});
    });

    setStatus("단일 DB 로딩 완료 (data/derived/master_db.js 없음)");
  } catch (e) {
    console.error(e);
    setStatus("로딩 실패: data/derived/master_db.js 또는 web_database.js/json을 확인하세요");
    el("emptyState").classList.remove("hidden");
  }
})();


/* 语义搜索：输入防抖/回车、结果卡（similarity/归属 chips）、点开详情 */

import { registerView, pending } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, viewHead, openDrawerById } from "./_shared.js";

let timer = null;

function hitHtml(h) {
  const sim = Number(h.similarity ?? 0);
  const md = h.metadata || {};
  const source = md.source_file || h.source_file || "";
  return `<button type="button" class="vlist-row" data-id="${esc(h.drawer_id || "")}" style="align-items:flex-start">
    <div style="flex:1;min-width:0">
      <div class="row" style="gap:6px;margin-bottom:4px">
        <span class="chip">${esc(h.wing || "?")}</span>
        <span class="chip">${esc(h.room || "?")}</span>
        <span class="chip" style="max-width:260px;overflow:hidden;text-overflow:ellipsis" title="${esc(
          source
        )}">${esc(source.split(/[\\/]/).pop() || "-")}</span>
        <span class="mono muted" style="font-size:11px">${esc(
          String(md.filed_at || "").slice(0, 10)
        )}</span>
      </div>
      <div style="font-size:13px;color:var(--fg-mid);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">
        ${esc((h.text ?? h.content_preview ?? "").slice(0, 300))}
      </div>
    </div>
    <div style="width:110px;flex-shrink:0">
      <div class="bar"><i style="width:${Math.min(100, Math.max(0, sim * 100)).toFixed(0)}%;background:var(--accent)"></i></div>
      <div class="mono muted" style="font-size:11px;text-align:right;margin-top:2px">sim ${sim.toFixed(3)}</div>
    </div>
  </button>`;
}

export async function renderSearchResults(query, holder) {
  const t0 = performance.now();
  holder.innerHTML = `<div class="skeleton" style="height:180px"></div>`;
  try {
    const body = await api("/api/search", { q: query, limit: 20 });
    const ms = Math.round(performance.now() - t0);
    const hits = body.data?.hits || body.data?.results || body.data || [];
    const list = Array.isArray(hits) ? hits : hits.drawers || [];
    if (!list.length) {
      holder.innerHTML = `<div class="alert is-warn">${t("se.noHit", { ms })}</div>`;
      return;
    }
    holder.innerHTML = `
      <div class="row mb-4" style="justify-content:space-between">
        <span class="muted" style="font-size:13px">${t("se.hitCount", { n: list.length, ms })}</span>
        <span class="row">${(body.tiers && Object.entries(body.tiers).map(([k, v]) => `<span class="chip ${v === "ok" ? "is-ok" : ""}">${k}=${v}</span>`).join(" ")) || ""}</span>
      </div>
      <div class="vlist">${list.map(hitHtml).join("")}</div>`;
    holder.querySelectorAll(".vlist-row").forEach((row) => {
      row.addEventListener("click", () => {
        if (row.dataset.id) openDrawerById(row.dataset.id);
      });
    });
  } catch (err) {
    holder.innerHTML = `<div class="alert is-err">${t("se.failed", { msg: esc(err.message) })}</div>`;
  }
}

function wireInput(input, holder) {
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      clearTimeout(timer);
      renderSearchResults(input.value.trim(), holder);
    }
  });
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = input.value.trim();
      if (q.length >= 2) renderSearchResults(q, holder);
    }, 300);
  });
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("se.title"), t("se.sub"))}
    <div class="card">
      <div class="row">
        <input id="search-input" name="q" type="search" autocomplete="off" class="grow" placeholder="${t("se.ph")}" style="width:100%">
      </div>
    </div>
    <div id="search-results" class="mt-4"></div>`;
  const input = container.querySelector("#search-input");
  const holder = container.querySelector("#search-results");
  wireInput(input, holder);
  if (window.matchMedia("(min-width: 900px)").matches) {
    input.focus();
  }
  if (pending.q) {
    const q = pending.q;
    pending.q = null;
    input.value = q;
    renderSearchResults(q, holder);
  }
}

registerView("search", render);

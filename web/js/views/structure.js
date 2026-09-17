/* 结构浏览：wing→room 树 + 抽屉分页列表 + 全文详情侧滑 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import {
  api,
  esc,
  num,
  viewHead,
  openDrawerById,
  drawerMetaHtml,
} from "./_shared.js";

const state = {
  taxonomy: null,
  wing: null,
  room: null,
  offset: 0,
  limit: 20,
  items: [],
  total: 0,
};

function treeHtml(tax) {
  const wings = Object.entries(tax || {}).sort();
  return wings
    .map(([wing, rooms]) => {
      const total = Object.values(rooms || {}).reduce((a, b) => a + b, 0);
      const roomRows = Object.entries(rooms || {})
        .sort((a, b) => b[1] - a[1])
        .map(
          ([room, c]) => `<a href="javascript:void 0" data-wing="${esc(wing)}" data-room="${esc(room)}"
            style="display:flex;justify-content:space-between;padding:3px 10px 3px 24px;
            border-radius:6px;color:var(--fg-low);font-size:12px;cursor:pointer">
            <span>${esc(room)}</span><span class="mono" style="font-size:11px">${c}</span></a>`
        )
        .join("");
      return `<div style="margin-bottom:12px">
        <a href="javascript:void 0" data-wing="${esc(wing)}" class="st-wing"
          style="display:flex;justify-content:space-between;padding:4px 10px;border-radius:6px;
          color:var(--fg);cursor:pointer;font-weight:600;font-size:13px;text-decoration:none">
          <span>${esc(wing)}</span><span class="mono" style="font-size:11px;color:var(--fg-low)">${num(total)}</span></a>
        ${roomRows}</div>`;
    })
    .join("");
}

function rowsHtml() {
  if (!state.items.length) {
    return `<div class="alert is-warn">${t("st.emptyRoom")}</div>`;
  }
  return state.items
    .map(
      (d) => `<button type="button" class="vlist-row" data-id="${esc(d.drawer_id || "")}">
        <span class="mono muted" style="font-size:11px;flex-shrink:0;width:86px">${esc(
          String((d.metadata || {}).filed_at || "").slice(0, 10) || "—"
        )}</span>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0">${esc(
          (d.content_preview || "").slice(0, 160) || t("st.emptyCell")
        )}</span>
      </button>`
    )
    .join("");
}

async function loadDrawers() {
  const holder = document.getElementById("structure-list");
  if (!holder) return;
  holder.innerHTML = `<div class="skeleton" style="height:220px"></div>`;
  const params = { offset: state.offset, limit: state.limit };
  if (state.wing) params.wing = state.wing;
  if (state.room) params.room = state.room;
  try {
    const body = await api("/api/drawers", params);
    state.items = body.data.drawers || [];
    state.total = body.data.total || 0;
  } catch (err) {
    holder.innerHTML = `<div class="alert is-err">${t("app.loadFailed", { msg: esc(err.message) })}</div>`;
    return;
  }
  const from = state.items.length ? state.offset + 1 : 0;
  const to = state.offset + state.items.length;
  holder.innerHTML = `
    <div class="row mb-4" style="justify-content:space-between">
      <span class="muted" style="font-size:13px;min-width:0;overflow-wrap:anywhere" id="structure-filter">${esc(
        state.wing || t("st.allWings")
      )}${state.room ? " / " + esc(state.room) : ""}${t("st.count", { total: num(state.total), from: num(from), to: num(to) })}</span>
      <span class="row">
        <button id="pg-prev" ${state.offset <= 0 ? "disabled" : ""}>${t("st.prev")}</button>
        <button id="pg-next" ${to >= state.total ? "disabled" : ""}>${t("st.next")}</button>
      </span>
    </div>
    <div class="vlist">${rowsHtml()}</div>`;
  holder.querySelectorAll(".vlist-row").forEach((row) => {
    row.addEventListener("click", () => openDrawerById(row.dataset.id));
  });
  const prev = holder.querySelector("#pg-prev");
  const next = holder.querySelector("#pg-next");
  if (prev)
    prev.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      loadDrawers();
    });
  if (next)
    next.addEventListener("click", () => {
      state.offset += state.limit;
      loadDrawers();
    });
}

function markSelected(container, el) {
  container
    .querySelectorAll(".st-selected")
    .forEach((n) => n.classList.remove("st-selected"));
  if (el) el.classList.add("st-selected");
}

async function render(container) {
  if (!state.taxonomy) {
    state.taxonomy = (await api("/api/taxonomy")).data;
  }
  const tax = state.taxonomy;
  if (!state.wing) {
    state.wing = Object.keys(tax)[0] || null;
  }

  container.innerHTML = `
    ${viewHead(t("st.title"), t("st.sub"))}
    <div class="grid structure-grid">
      <div class="card" id="structure-tree" style="max-height:70vh;overflow-y:auto">${treeHtml(tax)}</div>
      <div class="card" id="structure-list"></div>
    </div>`;

  container.querySelectorAll("[data-room]").forEach((a) => {
    a.addEventListener("click", () => {
      state.room = a.dataset.room;
      state.wing = a.dataset.wing;
      state.offset = 0;
      markSelected(container, a);
      loadDrawers();
    });
  });
  container.querySelectorAll("[data-wing]:not([data-room])").forEach((a) => {
    a.addEventListener("click", () => {
      state.wing = a.dataset.wing;
      state.room = null;
      state.offset = 0;
      markSelected(container, a);
      loadDrawers();
    });
  });

  await loadDrawers();
}

registerView("structure", render);

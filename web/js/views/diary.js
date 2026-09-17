/* Diary：agent 从宫殿数据推导（带 diary 房间的 wing）+ 手输，条目卡可展开 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, card, viewHead, timeShort } from "./_shared.js";

function agentsFromTaxonomy(tax) {
  const preferred = [];
  const others = [];
  for (const [wing, rooms] of Object.entries(tax || {})) {
    if (rooms && rooms.diary) {
      if (wing.startsWith("wing_")) preferred.push(wing.slice(5));
      else others.push(wing);
    }
  }
  return [...new Set([...preferred, ...others])];
}

async function load(agent, holder, countEl) {
  holder.innerHTML = `<div class="skeleton" style="height:160px"></div>`;
  try {
    const body = await api("/api/diary", { agent, last_n: 50 });
    const data = body.data || {};
    const entries =
      data.entries || data.results || (Array.isArray(data) ? data : []);
    if (countEl)
      countEl.textContent = t("dy.count", { n: entries.length, agent });
    if (!entries.length) {
      holder.innerHTML = `<div class="alert is-warn">${t("dy.noneFor", { agent: esc(agent) })}</div>`;
      return 0;
    }
    holder.innerHTML = entries
      .map((e) => entryHtml(e))
      .reverse()
      .join("");
    wire(holder);
    return entries.length;
  } catch (err) {
    holder.innerHTML = `<div class="alert is-err">${t("app.loadFailed", { msg: esc(err.message) })}</div>`;
    return -1;
  }
}

const EXPAND_THRESHOLD = 240;

function entryHtml(e) {
  const text = e.entry || e.content || "";
  const needsExpand = text.length > EXPAND_THRESHOLD;
  return `<div class="card" style="margin-bottom:12px">
    <div class="row" style="justify-content:space-between;margin-bottom:8px">
      <span class="row">
        <span class="chip">${esc(e.topic || "general")}</span>
        <span class="mono muted" style="font-size:11px">${timeShort(e.timestamp || e.created_at)}</span>
      </span>
      <span class="mono muted" style="font-size:11px">${esc(e.agent_name || "")}</span>
    </div>
    <pre class="code diary-text"${needsExpand ? ' data-truncated="1"' : ""} style="max-height:${
    needsExpand ? "96px" : "none"
  };overflow:${needsExpand ? "hidden" : "visible"}">${esc(text)}</pre>
    ${needsExpand ? `<button class="diary-expand" style="margin-top:8px">${t("dy.expand")}</button>` : ""}
  </div>`;
}

function wire(container) {
  container.querySelectorAll(".diary-expand").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pre = btn.parentElement.querySelector(".diary-text");
      if (!pre) return;
      if (pre.dataset.truncated === "1") {
        pre.dataset.truncated = "0";
        pre.style.maxHeight = "none";
        pre.style.overflow = "visible";
        btn.textContent = t("dy.collapse");
      } else {
        pre.dataset.truncated = "1";
        pre.style.maxHeight = "96px";
        pre.style.overflow = "hidden";
        btn.textContent = t("dy.expand");
      }
    });
  });
}

async function render(container) {
  let agents = [];
  try {
    const tax = (await api("/api/taxonomy")).data || {};
    agents = agentsFromTaxonomy(tax);
  } catch {
    agents = [];
  }

  container.innerHTML = `
    ${viewHead(t("dy.title"), t("dy.sub"))}
    <div class="card mb-4">
      <h3 class="card-title">${t("ui.introTitle")}</h3>
      <div class="muted" style="font-size:13px;line-height:1.9">
        ${t("dy.intro")}
      </div>
    </div>
    <div class="card">
      <div class="row">
        <span class="muted" style="font-size:13px">${t("dy.agentLabel")}</span>
        ${agents
          .map((p) => `<button class="diary-preset" data-agent="${esc(p)}">${esc(p)}</button>`)
          .join(" ")}
        <input id="diary-agent" name="agent" autocomplete="off" placeholder="${t("dy.agentPh")}" style="width:200px">
        <button id="diary-go" class="btn-primary">${t("dy.load")}</button>
        <span id="diary-count" class="muted grow" style="text-align:right;font-size:12px"></span>
      </div>
    </div>
    <div id="diary-list" class="mt-4"></div>`;

  const input = container.querySelector("#diary-agent");
  const holder = container.querySelector("#diary-list");
  const countEl = container.querySelector("#diary-count");

  container.querySelectorAll(".diary-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      input.value = btn.dataset.agent;
      load(btn.dataset.agent, holder, countEl);
    });
  });
  container.querySelector("#diary-go").addEventListener("click", () => {
    const agent = input.value.trim();
    if (agent) load(agent, holder, countEl);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const agent = input.value.trim();
      if (agent) load(agent, holder, countEl);
    }
  });

  if (agents.length) {
    input.value = agents[0];
    for (const agent of agents.slice(0, 3)) {
      const n = await load(agent, holder, countEl);
      if (n > 0) {
        input.value = agent;
        break;
      }
    }
  } else {
    holder.innerHTML = `<div class="muted" style="font-size:13px">${t("dy.noAgents")}</div>`;
  }
}

registerView("diary", render);

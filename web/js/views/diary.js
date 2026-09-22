/* Diary：预设 agent 来自真实条目（/api/diary/agents，按数量降序）+ 手输兜底；
   首屏 20 条 + 加载更多（单次 last_n=50 封顶），选中 chip 高亮且不回填输入框。 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, card, viewHead, timeShort } from "./_shared.js";

const PAGE_SIZE = 20;
const EXPAND_THRESHOLD = 240;

async function render(container) {
  let agents = [];
  try {
    agents = (await api("/api/diary/agents")).data || [];
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
          .map(
            (p) =>
              `<button class="diary-preset" data-agent="${esc(p)}" aria-pressed="false">${esc(p)}</button>`
          )
          .join(" ")}
        <input id="diary-agent" name="agent" autocomplete="off" placeholder="${t("dy.agentPh")}" style="width:220px">
        <button id="diary-go" class="btn-primary">${t("dy.load")}</button>
        <span id="diary-count" class="muted grow" style="text-align:right;font-size:12px"></span>
      </div>
    </div>
    <div id="diary-list" class="mt-4"></div>`;

  const input = container.querySelector("#diary-agent");
  const holder = container.querySelector("#diary-list");
  const countEl = container.querySelector("#diary-count");

  let entries = [];
  let shown = 0;

  function renderEntries() {
    const slice = entries.slice(0, shown);
    const more =
      entries.length > shown
        ? `<button type="button" class="diary-more">${t("dy.loadMore", {
            n: entries.length - shown,
          })}</button>`
        : "";
    holder.innerHTML = slice.map((e) => entryHtml(e)).join("") + more;
    wire(holder);
    const btn = holder.querySelector(".diary-more");
    if (btn) {
      btn.addEventListener("click", () => {
        shown = Math.min(shown + PAGE_SIZE, entries.length);
        renderEntries();
      });
    }
  }

  async function load(agent) {
    holder.innerHTML = `<div class="skeleton" style="height:160px"></div>`;
    try {
      const body = await api("/api/diary", { agent, last_n: 50 });
      const data = body.data || {};
      const raw = data.entries || data.results || (Array.isArray(data) ? data : []);
      entries = raw.slice().reverse();
      shown = Math.min(PAGE_SIZE, entries.length);
      if (countEl) countEl.textContent = t("dy.count", { n: entries.length, agent });
      if (!entries.length) {
        holder.innerHTML = `<div class="alert is-warn">${t("dy.noneFor", {
          agent: esc(agent),
        })}</div>`;
        return 0;
      }
      renderEntries();
      return entries.length;
    } catch (err) {
      holder.innerHTML = `<div class="alert is-err">${t("app.loadFailed", {
        msg: esc(err.message),
      })}</div>`;
      return -1;
    }
  }

  function setActive(agent) {
    container.querySelectorAll(".diary-preset").forEach((b) => {
      const on = b.dataset.agent === agent;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  container.querySelectorAll(".diary-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      input.value = "";
      setActive(btn.dataset.agent);
      void load(btn.dataset.agent);
    });
  });

  const loadFromInput = () => {
    const agent = input.value.trim();
    if (agent) {
      setActive("");
      void load(agent);
    }
  };
  container.querySelector("#diary-go").addEventListener("click", loadFromInput);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadFromInput();
  });

  if (agents.length) {
    setActive(agents[0]);
    await load(agents[0]);
  } else {
    holder.innerHTML = `<div class="muted" style="font-size:13px">${t("dy.noAgents")}</div>`;
  }
}

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
    ${
      needsExpand
        ? `<button class="diary-expand" style="margin-top:8px">${t("dy.expand")}</button>`
        : ""
    }
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

registerView("diary", render);

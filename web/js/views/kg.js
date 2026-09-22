/* 知识图谱：stats 大卡 + ECharts 力导向图（点击节点查事实）+ 时间线 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, num, card, viewHead, chip, timeShort, cssColor } from "./_shared.js";

let chart = null;
let resizeHandler = null;

function factsList(facts) {
  if (!facts.length) {
    return `<div class="alert is-warn">${t("kg.noFacts")}</div>`;
  }
  return `<table class="tbl">
    <tr><th>${t("kg.thSubject")}</th><th>${t("kg.thPredicate")}</th><th>${t("kg.thObject")}</th><th>${t("kg.thStatus")}</th><th>${t("kg.thFrom")}</th></tr>
    ${facts
      .map(
        (f) => `<tr>
        <td class="kg-entity mono" style="font-size:12px;cursor:pointer">${esc(
          f.subject || "—"
        )}</td>
        <td class="mono" style="font-size:12px">${esc(f.predicate || "")}</td>
        <td>${esc(f.object || "")}</td>
        <td>${f.current ? chip(t("kg.chipCurrent"), "is-ok") : chip(t("kg.chipExpired"), "is-err")}</td>
        <td class="mono muted" style="font-size:11px">${f.valid_from ? timeShort(f.valid_from) : "—"}</td>
      </tr>`
      )
      .join("")}
  </table>`;
}

function graphOption(facts) {
  const accent = cssColor("var(--accent)");
  const violet = cssColor("var(--violet-400)");
  const inkDim = cssColor("var(--ink-500)");
  const edgeStrong = cssColor("var(--ink-300)");
  const edgeMention = cssColor("var(--ink-400)");
  const nodes = new Map();
  const edges = [];
  for (const f of facts) {
    const s = String(f.subject || "").trim();
    const o = String(f.object || "").trim();
    if (!s || !o) continue;
    const sNode = nodes.get(s);
    if (!sNode) {
      nodes.set(s, {
        id: s,
        name: s,
        symbolSize: 34,
        itemStyle: { color: violet },
      });
    } else {
      sNode.symbolSize = 34;
      sNode.itemStyle = { color: violet };
      sNode.label = { show: true };
    }
    if (!nodes.has(o))
      nodes.set(o, {
        id: o,
        name: o,
        symbolSize: 24,
        itemStyle: { color: f.current ? accent : inkDim },
        label: { show: false },
      });
    edges.push({
      source: s,
      target: o,
      lineStyle: {
        color: f.current ? edgeStrong : inkDim,
        opacity: f.current ? 0.9 : 0.45,
      },
    });
  }

  /* 提及边：事实文本中字面出现的其他实体（词边界、按对去重；虚线与实线事实边区分） */
  const subjects = new Set(
    facts.map((x) => String(x.subject || "").trim()).filter(Boolean)
  );
  const seenMention = new Set();
  const escRe = (v) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const f of facts) {
    const s = String(f.subject || "").trim();
    const o = String(f.object || "").trim();
    if (!s || o.length < 10) continue;
    for (const ent of subjects) {
      if (ent === s || ent === o || ent.length < 5) continue;
      const re = new RegExp(
        `(?<![A-Za-z0-9_])${escRe(ent)}(?![A-Za-z0-9_])`, "i"
      );
      if (!re.test(o)) continue;
      const key = `${s}\u0000${ent}`;
      if (seenMention.has(key)) continue;
      seenMention.add(key);
      edges.push({
        source: s,
        target: ent,
        mention: true,
        snippet: o.slice(0, 160),
        lineStyle: { color: edgeMention, opacity: 0.6, width: 1, type: "dashed" },
      });
    }
  }
  return {
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p) => {
        if (p.dataType !== "edge") return esc(String(p.name ?? ""));
        const d = p.data;
        if (d.mention) {
          return `${t("kg.mentionEdge", {
            from: esc(String(d.source)),
            to: esc(String(d.target)),
          })}<br><span style="font-size:11px;opacity:.75">${esc(String(d.snippet || ""))}…</span>`;
        }
        return `${esc(String(d.source))} → ${esc(String(d.target))}`;
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        label: {
          show: true,
          position: "right",
          formatter: (p) => {
            const v = String(p && p.name != null ? p.name : p || "");
            return v.length > 16 ? `${v.slice(0, 15)}…` : v;
          },
          color: cssColor("var(--ink-000)"),
          fontFamily: "monospace",
          fontSize: 10,
          textBorderColor: cssColor("var(--bg-deep)"),
          textBorderWidth: 3,
        },
        labelLayout: { hideOverlap: true },
        force: { repulsion: 1000, edgeLength: 150, gravity: 0.06 },
        data: [...nodes.values()],
        links: edges,
      },
    ],
  };
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("kg.title"), t("kg.sub"))}
    <div class="grid grid-3">
      <div class="card"><div class="stat-num" id="kg-entities">…</div><div class="stat-label">${t("kg.statEntities")}</div></div>
      <div class="card"><div class="stat-num" id="kg-triples">…</div><div class="stat-label">${t("kg.statTriples")}</div></div>
      <div class="card"><div class="stat-num" id="kg-current">…</div><div class="stat-label">${t("kg.statCurrent")}</div><div id="kg-expired-line" class="muted" style="font-size:11px"></div></div>
    </div>
    <div class="card mt-4">
      <h3 class="card-title">${t("kg.chart")}</h3>
      <div id="kg-chart" style="height:620px"></div>
    </div>
    <div class="card mt-4" id="kg-facts-card">
      <h3 class="card-title">${t("kg.factsCard")}</h3>
      <div id="kg-facts"><div class="muted" style="font-size:13px">${t("kg.noEntity")}</div></div>
    </div>
    <div class="card mt-4">
      <h3 class="card-title">${t("kg.timeline")}</h3>
      <div id="kg-timeline" style="max-height:420px;overflow-y:auto"></div>
    </div>`;

  const stats = (await api("/api/kg/stats")).data || {};
  container.querySelector("#kg-entities").textContent = num(stats.entities);
  container.querySelector("#kg-triples").textContent = num(stats.triples);
  container.querySelector("#kg-current").textContent = num(stats.current_facts);
  if (stats.expired_facts > 0) {
    container.querySelector("#kg-expired-line").textContent = t("kg.expired", {
      n: num(stats.expired_facts),
    });
  }

  const tl = (await api("/api/kg/timeline")).data || {};
  const facts = tl.timeline || tl.facts || tl.results || [];
  const sortedFacts = [...facts].sort((a, b) =>
    String(b.valid_from || "").localeCompare(String(a.valid_from || ""))
  );
  container.querySelector("#kg-timeline").innerHTML = factsList(sortedFacts.slice(0, 100));
  container.querySelectorAll("#kg-timeline .kg-entity").forEach((td) => {
    const entity = td.textContent.trim();
    if (entity && entity !== "—") {
      td.addEventListener("click", () => loadFacts(entity));
    }
  });

  const chartDom = container.querySelector("#kg-chart");
  if (chart && !chart.isDisposed()) chart.dispose();
  chart = echarts.init(chartDom);
  chart.setOption(graphOption(facts.slice(0, 300)));

  /* 自动适配全貌：轮询到布局稳定后把全部节点+关系连线框进画布（只适配一次，不覆盖手动缩放） */
  const c = chart;
  let fitted = false;
  let prevKey = "";
  let stable = 0;
  let ticks = 0;
  const fitTimer = setInterval(() => {
    if (fitted || c.isDisposed()) {
      clearInterval(fitTimer);
      return;
    }
    ticks += 1;
    try {
      const data = c.getModel().getSeriesByIndex(0).getData();
      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;
      for (let i = 0; i < data.count(); i += 1) {
        const layout = data.getItemLayout(i);
        if (!layout) continue;
        if (layout[0] < minX) minX = layout[0];
        if (layout[0] > maxX) maxX = layout[0];
        if (layout[1] < minY) minY = layout[1];
        if (layout[1] > maxY) maxY = layout[1];
      }
      if (!Number.isFinite(minX)) return;
      const key = `${Math.round(minX)},${Math.round(maxX)},${Math.round(minY)},${Math.round(maxY)}`;
      if (key === prevKey) stable += 1;
      else stable = 0;
      prevKey = key;
      /* 边稳边跟：布局期间每轮都适配（视图跟随），连续两轮不动或超时后收手 */
      const cw = c.getWidth();
      const ch = c.getHeight();
      const pad = 100;
      const zoom = Math.min(
        1,
        (cw - pad) / Math.max(1, maxX - minX),
        (ch - pad) / Math.max(1, maxY - minY)
      );
      if (zoom < 0.999) {
        c.setOption({
          series: [{ zoom, center: [(minX + maxX) / 2, (minY + maxY) / 2] }],
        });
      }
      if (stable >= 2 || ticks >= 24) {
        fitted = true;
        clearInterval(fitTimer);
      }
    } catch {
      /* 内部 API 不可用则放弃适配，不影响页面 */
      fitted = true;
      clearInterval(fitTimer);
    }
  }, 500);
  chart.on("click", (p) => {
    if (p.componentType !== "series" || p.dataType !== "node" || !p.name) return;
    void loadFacts(p.name);
  });

  async function loadFacts(entity) {
    const holder = document.getElementById("kg-facts");
    if (holder) holder.innerHTML = `<div class="skeleton" style="height:80px"></div>`;
    try {
      const body = await api("/api/kg/query", { entity });
      const raw = body.data?.facts || body.data || [];
      const list = Array.isArray(raw) ? raw : raw.facts || [];
      if (holder) holder.innerHTML = factsList(list);
    } catch (err) {
      if (holder) holder.innerHTML = `<div class="alert is-err">${esc(err.message)}</div>`;
    }
    const card = document.getElementById("kg-facts-card");
    if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  if (resizeHandler) window.removeEventListener("resize", resizeHandler);
  resizeHandler = () => {
    if (chart && !chart.isDisposed()) chart.resize();
  };
  window.addEventListener("resize", resizeHandler);
}

registerView("kg", render);

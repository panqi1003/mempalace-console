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
  const inkFaint = cssColor("var(--ink-600)");
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
        color: f.current ? inkDim : inkFaint,
        opacity: f.current ? 0.8 : 0.35,
      },
    });
  }
  return {
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p) =>
        p.dataType === "edge"
          ? `${esc(String(p.data.source))} → ${esc(String(p.data.target))}`
          : esc(String(p.name ?? "")),
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
          color: cssColor("var(--ink-000)"),
          fontFamily: "monospace",
          fontSize: 10,
          textBorderColor: cssColor("var(--bg-deep)"),
          textBorderWidth: 3,
        },
        labelLayout: { hideOverlap: true },
        force: { repulsion: 420, edgeLength: 110, gravity: 0.08 },
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
    <div class="grid grid-2 mt-4">
      <div class="card"><h3 class="card-title">${t("kg.chart")}</h3>
        <div id="kg-chart" style="height:460px"></div>
      </div>
      <div class="card"><h3 class="card-title">${t("kg.timeline")}</h3>
        <div id="kg-timeline" style="max-height:460px;overflow-y:auto"></div>
      </div>
    </div>
    <div class="card mt-4" id="kg-facts-card">
      <h3 class="card-title">${t("kg.factsCard")}</h3>
      <div id="kg-facts"><div class="muted" style="font-size:13px">${t("kg.noEntity")}</div></div>
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

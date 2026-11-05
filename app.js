// Draws the data-driven parts of the page from data.json (written by update.py).
"use strict";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Escape, then turn `code` and **bold** from the markdown sources into tags.
const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
const num = (n) => Number(n).toLocaleString("en-AU");
const money = (n) => "$" + Number(n).toLocaleString("en-AU", { maximumFractionDigits: 2 });
// Times are shown in the repo's own offset (+10:00), not the reader's zone.
const local = (iso) => {
  const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso);
  return { day: `${m[1]}-${m[2]}-${m[3]}`, time: `${m[4]}:${m[5]}` };
};
const dayName = (d) => new Date(d + "T12:00:00Z").toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const KINDS = { plan: "Plan", process: "Process", milestone: "Milestone", incident: "Incident", review: "Review", test: "Tests" };
const SVG = "http://www.w3.org/2000/svg";

function heroAndStats(d) {
  const s = d.stats;
  const hours = (Date.parse(s.last_commit) - Date.parse(s.first_commit)) / 3.6e6;
  const agents = document.querySelectorAll(".agents tbody tr").length;
  $("#hero-stats").innerHTML = [
    [num(s.commits), "commits"], [num(s.tests_passing), "tests passing"], [s.products, "products"],
    [s.licences, "licences"], [`~${Math.round(hours)} h`, "of building"],
  ].map(([v, l]) => `<span><b>${v}</b> ${l}</span>`).join("");
  const cards = [
    [num(s.tests_passing), "tests passing, 0 failing", true],
    [num(s.commits), "commits on main"],
    [`~${Math.round(hours)} h`, "first commit to latest"],
    [agents, "agents (2 still running)"],
    [s.products, "products"],
    [s.licences, "licences"],
    [s.fixtures, "fixture types"],
    [s.levels, "levels"],
    [s.models, ".glb models"],
    [s.sounds, "sound files"],
    [s.music_tracks, "music tracks", true],
    [s.test_files, "test case files"],
    [s.gd_files, "GDScript files"],
    [num(s.gd_lines), "lines of GDScript"],
  ];
  $("#stats").innerHTML = cards.map(([v, l, g]) => `<div class="stat${g ? " gold" : ""}"><b>${v}</b><span>${l}</span></div>`).join("");
}

function timeline(d) {
  const used = new Set(d.events.map((e) => e.kind));
  $("#tl-legend").innerHTML = Object.entries(KINDS).filter(([k]) => used.has(k))
    .map(([k, v]) => `<span class="k-${k}">${v}</span>`).join("");
  let html = "", day = "";
  for (const e of d.events) {
    const t = local(e.date);
    if (t.day !== day) { day = t.day; html += `<li class="day">${dayName(day)}</li>`; }
    html += `<li class="k-${e.kind}"><div class="ev"><time datetime="${esc(e.date)}">${t.time}</time>` +
      `<span class="kind">${KINDS[e.kind] || esc(e.kind)}</span><h4>${md(e.title)}</h4><p>${md(e.text)}</p></div></li>`;
  }
  $("#tl").innerHTML = html;
  $("#commit-count").textContent = `${d.commits.length} commits`;
  $("#commit-list").innerHTML = d.commits.slice().reverse().map((c) => {
    const t = local(c.date);
    return `<li><span>${t.day.slice(5)} ${t.time}</span><span>${esc(c.sha)}</span>${esc(c.subject)}</li>`;
  }).join("");
}

function el(name, attrs, parent, text) {
  const n = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  if (parent) parent.appendChild(n);
  return n;
}

function hourLabel(ms) {
  // Hour of day at +10:00.
  const h = new Date(ms + 10 * 3.6e6).getUTCHours();
  return String(h).padStart(2, "0") + ":00";
}

function testChart(d) {
  const pts = d.test_points.map((p) => ({ ...p, t: Date.parse(p.date) }));
  const W = 860, H = 300, L = 48, R = 20, T = 24, B = 34;
  const t0 = Math.floor((pts[0].t - 1800e3) / 3.6e6) * 3.6e6;
  const t1 = Math.ceil((pts[pts.length - 1].t + 1800e3) / 3.6e6) * 3.6e6;
  const yMax = Math.ceil(Math.max(...pts.map((p) => p.passed)) / 250) * 250;
  const x = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Full-suite tests passed over time" });
  for (let v = 0; v <= yMax; v += 250) {
    el("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "axis" }, svg);
    el("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, svg, num(v));
  }
  for (let t = t0; t <= t1; t += 2 * 3.6e6) el("text", { x: x(t), y: H - 12, "text-anchor": "middle" }, svg, hourLabel(t));
  const line = pts.map((p) => `${x(p.t).toFixed(1)},${y(p.passed).toFixed(1)}`).join(" L");
  el("path", { d: `M${x(pts[0].t)},${y(0)} L${line} L${x(pts[pts.length - 1].t)},${y(0)}Z`, class: "area" }, svg);
  el("path", { d: "M" + line, class: "line" }, svg);
  let lastX = -1e9, flip = false;
  for (const p of pts) {
    const px = x(p.t), py = y(p.passed);
    const dot = el("circle", { cx: px, cy: py, r: 5.5, class: p.failed ? "dot fail" : "dot" }, svg);
    el("title", {}, dot, `${local(p.date).time}: ${num(p.passed)} passed, ${p.failed} failed (${p.source})`);
    flip = px - lastX < 40 ? !flip : false; // stagger labels of runs close in time
    lastX = px;
    const label = num(p.passed) + (p.failed ? ` / ${p.failed}✗` : "");
    el("text", { x: px, y: flip ? py + 20 : py - 10, "text-anchor": "middle", class: "lbl" }, svg, label);
  }
  $("#test-chart").replaceChildren(svg);
}

function commitChart(d) {
  const hrs = d.commits_per_hour;
  const W = 860, H = 200, L = 30, R = 10, T = 16, B = 30;
  const max = Math.max(...hrs.map((h) => h.commits));
  const bw = (W - L - R) / hrs.length;
  const y = (v) => T + (1 - v / max) * (H - T - B);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Commits per hour" });
  el("line", { x1: L, x2: W - R, y1: y(0), y2: y(0), class: "axis" }, svg);
  hrs.forEach((h, i) => {
    const bx = L + i * bw;
    if (h.commits) {
      const r = el("rect", { x: bx + 3, y: y(h.commits), width: bw - 6, height: y(0) - y(h.commits), rx: 3, class: "bar" }, svg);
      el("title", {}, r, `${local(h.hour).day} ${local(h.hour).time}: ${h.commits} commits`);
      el("text", { x: bx + bw / 2, y: y(h.commits) - 4, "text-anchor": "middle", class: "lbl" }, svg, h.commits);
    }
    if (i % 2 === 0) el("text", { x: bx + bw / 2, y: H - 10, "text-anchor": "middle" }, svg, local(h.hour).time);
  });
  $("#commit-chart").replaceChildren(svg);
}

function table(sel, head, rows, numCols = []) {
  const t = $(sel);
  const cls = (i) => (numCols.includes(i) ? ' class="num"' : "");
  t.insertAdjacentHTML("beforeend",
    `<thead><tr>${head.map((h, i) => `<th${cls(i)}>${esc(h)}</th>`).join("")}</tr></thead>` +
    `<tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${cls(i)}>${c}</td>`).join("")}</tr>`).join("")}</tbody>`);
}

function economy(d) {
  const e = d.economy;
  $("#start-cash").textContent = money(e.start_cash);
  const [ph, ...pr] = e.pacing;
  table("#pacing", ph, pr.map((r) => r.map(esc)));
  table("#licences", ["Licence", "Level", "Price", "Needs"],
    e.licences.map((l) => [esc(l.name), l.level, l.price ? money(l.price) : "free", esc(l.needs || "")]), [1, 2]);
  table("#expansions", ["Id", "Expansion", "Level", "Price", "Daily rent after"],
    [["Start", "12 × 8 m shop", 1, "-", money(e.start_rent)].map(String),
     ...e.expansions.map((x) => [x.id, esc(x.name), x.level, money(x.price), money(x.rent_after)])], [2, 3, 4]);
  table("#stockroom", ["Id", "Stage", "Level", "Price", "Rent added"],
    e.stockroom.map((x) => [x.id, esc(x.name), x.level, money(x.price), "+" + money(x.rent_add)]), [2, 3, 4]);
}

function status(d) {
  $("#in-progress").innerHTML = d.in_progress.map((w) => {
    let tbl = "";
    if (w.table) {
      const res = (c) => (c === "ok" ? '<span class="ok">ok</span>' : c === "fails" ? '<span class="bad">fails</span>' : esc(c));
      tbl = `<div class="table-wrap"><table><caption>${esc(w.table.caption)}</caption><thead><tr>${w.table.head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>` +
        `<tbody>${w.table.rows.map((r) => `<tr>${r.map((c) => `<td>${res(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }
    return `<article class="card wip-card"><h3>${esc(w.title)}</h3><p class="who">${esc(w.who)}</p><p>${md(w.text)}</p>${tbl}</article>`;
  }).join("");
  const secs = d.sections.filter((s) => s.deferred.length);
  const total = secs.reduce((n, s) => n + s.deferred.length, 0);
  $("#deferred").innerHTML = `<p><b>${total}</b> deferred check groups across <b>${secs.length}</b> PROGRESS.md sections:</p>` +
    secs.map((s) => `<details><summary>${esc(s.title)}<small>${s.deferred.length}</small></summary><ul>${s.deferred.map((x) => `<li>${md(x)}</li>`).join("")}</ul></details>`).join("");
  $("#generated").textContent = d.generated.replace("T", " ");
  $("#head").textContent = d.head;
}

fetch("data.json", { cache: "no-cache" })
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((d) => { heroAndStats(d); timeline(d); testChart(d); commitChart(d); economy(d); status(d); })
  .catch((err) => { $("#tl").innerHTML = `<li class="loading">Couldn't load data.json (${esc(err.message)}).</li>`; });

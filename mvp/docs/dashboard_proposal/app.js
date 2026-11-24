const {inc, risks, inst, src} = D;
const TIERS = [["real_world", "Observed in real world"], ["synthetic", "Synthetic"], ["lab", "Lab"]];
const TIERDEF = {real_world: "Deployed systems acting on real stakes, outside experimenter control.",
  synthetic: "Agents interacting in a simulated or researcher-built environment.",
  lab: "A controlled experiment on real models in a narrow task probe, with no environment."};
const CHECK = {verified: "Primary source read in full and every claim checked against it.",
  partially_verified: "The primary source was read, and at least one claim in the dossier is not confirmed by it: the source is silent, hedged, or the claim rests on a secondary source. The dossier's verification notes name each such claim.",
  unverified: "Not yet checked against the primary source. A dossier written by Claude stays here until a person checks it."};
const SHORT = {aiid: "AIID", air_enkrypt: "Agent Incident Registry", aivillage: "AI Village", lesswrong: "LessWrong"};
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const instOf = Object.fromEntries(inst.map(i => [i.id, i]));
const riskOf = Object.fromEntries(risks.map(r => [r.id, r]));
const FMs = risks.filter(r => r.k === "Failure mode"), RFs = risks.filter(r => r.k === "Risk factor");
const nInst = id => inc.filter(x => x.i.includes(id)).length;
const abbr = (id, name) => `<abbr title="${esc(name)}">${id}</abbr>`;
const tierMark = t => `<i class="tier t-${t}" title="${t}"></i>`;
const tierName = t => TIERS.find(z => z[0] === t)[1];
const srcName = s => src[s]?.n || s;

/* ---- one filter for the whole page. A key is ";"-joined parts, each "kind:value", ANDed. */
const PRED = {
  fm: v => x => v === "none" ? !x.fm : x.fm === v,
  tier: v => x => x.e === v,
  inst: v => x => x.i.includes(v),
  src: v => x => x.s.includes(v),
  canon: v => x => x.c === v,
  also: v => x => x.c !== v && x.s.includes(v),
  year: v => x => x.d.startsWith(v),
  v: v => x => x.v === v,
  hasfm: () => x => !!x.fm,
  hasinst: () => x => x.i.length > 0,
};
const DESC = {
  fm: v => v === "none" ? ["No failure mode yet", "The facts read so far do not settle the Gate 2 tree."] : [`${v} ${riskOf[v].n}`, riskOf[v].d],
  tier: v => [tierName(v), TIERDEF[v]],
  inst: v => [`${v} ${instOf[v].n}`, `${instOf[v].d} The paper discusses it under ${instOf[v].r} ${riskOf[instOf[v].r].n}.`],
  src: v => [srcName(v), "Every incident this source reports."],
  canon: v => [srcName(v), "Incidents whose canonical source this is."],
  also: v => [srcName(v), "Incidents this source also reports, with another canonical source."],
  year: v => [`Event year ${v}`, "Incidents dated to this year. Studies are dated by publication."],
  v: v => [v.replace("_", " "), CHECK[v]],
  hasfm: () => ["Has a failure mode", "Incidents with a failure mode derived by the Gate 2 tree."],
  hasinst: () => ["Has an instance", "Incidents with at least one instance assigned."],
};
const parts = key => key.split(";").map(p => { const k = p.indexOf(":"); return [p.slice(0, k), p.slice(k + 1)]; });
let sel = null;   // the active key, or null
let tierChip = "all";
const matches = x => (!sel || parts(sel).every(([k, v]) => PRED[k](v)(x))) && (tierChip === "all" || x.e === tierChip);
const hit = (key, inner, cls = "") => `<span class="hit ${cls}" data-f="${key}" tabindex="0" role="button">${inner}</span>`;

// Fig. 0 sources
const srcIds = [...new Set(inc.flatMap(x => x.s))];
const srcRows = srcIds.map(s => ({s, canon: inc.filter(x => x.c === s).length, also: inc.filter(x => x.c !== s && x.s.includes(s)).length}))
  .sort((a, b) => b.canon + b.also - a.canon - a.also);
const smax = Math.max(...srcRows.map(r => r.canon + r.also));
document.getElementById("srckey").innerHTML = `<span><i class="sw t-real_world"></i>Canonical source</span><span><i class="sw t-lab"></i>Also reported here</span>`;
document.getElementById("srcs").innerHTML = srcRows.map(r => `
  <div>${hit("src:" + r.s, esc(srcName(r.s)))} <a class="ext" href="${esc(src[r.s]?.u || "#")}" title="Open ${esc(srcName(r.s))}">↗</a></div>
  <div class="track"><i class="t-real_world" data-f="canon:${r.s}" style="width:${r.canon / smax * 100}%"></i>${r.also ? `<i class="t-lab" data-f="also:${r.s}" style="width:${r.also / smax * 100}%"></i>` : ""}</div>
  <div class="n">${hit("canon:" + r.s, r.canon)}${r.also ? ` <small>${hit("also:" + r.s, "+" + r.also)}</small>` : ""}</div>`).join("");

// headline results
const nVer = inc.filter(x => x.v === "verified").length, nPart = inc.filter(x => x.v === "partially_verified").length;
const withFm = inc.filter(x => x.fm).length;
const fmSeen = FMs.filter(f => inc.some(x => x.fm === f.id)).length;
const instSeen = inst.filter(i => nInst(i.id)).length;
const fig = (key, v, of, l, sub, gap) => `<div class="${gap ? "gap" : ""}"><span class="v">${key ? hit(key, v) : v}${of ? `<small> / ${of}</small>` : ""}</span><span class="lab">${l}</span><span class="sub">${sub}</span></div>`;
document.getElementById("figs").innerHTML =
  fig("", inc.length, 0, "Multi-agent incidents", "in scope by a person's decision") +
  fig("v:verified", nVer, inc.length, "Verified", `${hit("v:partially_verified", nPart)} more partially verified`) +
  fig("hasfm:1", fmSeen, FMs.length, "Failure modes observed", `${withFm} of ${inc.length} incidents have one`, fmSeen < FMs.length) +
  fig("hasinst:1", instSeen, inst.length, "Instances observed", "at least one incident each", instSeen < inst.length);

// §1 failure modes, by the derived failure mode only
document.getElementById("key").innerHTML = TIERS.map(([t, l]) => hit("tier:" + t, `<i class="sw t-${t}"></i>${l}`, "keyitem")).join("");
const fmRows = [...FMs.map(f => ({id: f.id, n: f.n, u: inc.filter(x => x.fm === f.id)})), {id: "none", n: "No failure mode yet", u: inc.filter(x => !x.fm)}];
const max = Math.max(...fmRows.map(r => r.u.length));
document.getElementById("riskrows").innerHTML = fmRows.map(r => {
  const bars = TIERS.map(([t]) => { const n = r.u.filter(x => x.e === t).length;
    return n ? `<i class="t-${t}" data-f="fm:${r.id};tier:${t}" style="width:${n / max * 100}%" title="${n} ${t}"></i>` : ""; }).join("");
  return `<div class="nm"><span class="mono">${r.id === "none" ? "·" : r.id}</span>${hit("fm:" + r.id, esc(r.n), r.id === "none" ? "quiet" : "")}</div>
    <div class="track">${r.u.length ? bars : `<span class="none">no incident</span>`}</div>
    <div class="n${r.u.length ? "" : " z"}">${hit("fm:" + r.id, r.u.length)}</div>`; }).join("");
document.getElementById("fmcap").innerHTML = `<b>Fig. 1</b> A count of incidents, not a score. ${inc.length - withFm} incidents have no failure mode. 30 of them carry a security instance, I28 to I33: attacks, where none of the three modes fits by definition.`;

// §2 instance x failure-mode matrix
const cols = [...FMs.map(f => ({id: f.id, n: f.n})), {id: "none", n: "No failure mode yet"}];
const inCol = (x, c) => c.id === "none" ? !x.fm : x.fm === c.id;
const cmax = Math.max(...inst.flatMap(i => cols.map(c => inc.filter(x => inCol(x, c) && x.i.includes(i.id)).length)));
const dens = n => n === 0 ? "" : n >= Math.ceil(cmax * 2 / 3) ? "d3" : n >= Math.ceil(cmax / 3) ? "d2" : "d1";
let mx = `<thead><tr><th colspan="2">Instance</th>${cols.map(c => `<th class="num">${hit("fm:" + c.id, c.id === "none" ? "None" : c.id)}</th>`).join("")}<th class="num">All</th></tr></thead>`;
// one flat list in id order: grouping rows by the paper's FM/RF placement would cross RF blocks with FM columns
const placed = i => i.p === "ours" ? `Authored by this project, placed under ${i.r} ${riskOf[i.r].n}` : `Discussed under ${i.r} ${riskOf[i.r].n} in the paper`;
mx += `<tbody>`;
for (const i of inst) {
  const tot = nInst(i.id);
  mx += `<tr class="${tot ? "" : "z"}"><td class="id">${i.id}</td><td class="nm" title="${esc(placed(i))}">${tot ? hit("inst:" + i.id, esc(i.n)) : esc(i.n)}${i.p === "ours" ? `<span class="ours">ours</span>` : ""}</td>` +
    cols.map(c => { const n = inc.filter(x => inCol(x, c) && x.i.includes(i.id)).length;
      return `<td class="num${n ? "" : " zero"}">${n ? hit(`inst:${i.id};fm:${c.id}`, n, dens(n)) : "<span>·</span>"}</td>`; }).join("") +
    `<td class="num tot">${tot ? hit("inst:" + i.id, tot) : "<span>0</span>"}</td></tr>`;
}
mx += `</tbody>`;
document.getElementById("mx2").innerHTML = mx;

// §3 cumulative by year from the earliest incident, AIID full sourcing marked. Each year is a click band.
const years = inc.map(x => +x.d.slice(0, 4)), y0 = Math.min(...years), y1 = Math.max(...years), FULL = 2024;
const W = 840, H = 220, L = 34, R = 14, T = 24, B = 26;
const X = y => L + (y - y0) / (y1 + 1 - y0) * (W - L - R), Y = n => T + (1 - n / inc.length) * (H - T - B);
let cum = 0; const pts = [[X(y0), Y(0)]];
for (let y = y0; y <= y1; y++) { const k = years.filter(v => v === y).length; pts.push([X(y), Y(cum)]); cum += k; pts.push([X(y), Y(cum)]); }
pts.push([X(y1 + 1), Y(cum)]);
const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
const ticksY = [0, 10, 20, 30, 40, 50].filter(n => n <= inc.length);
const bands = []; for (let y = y0; y <= y1; y++) { const k = years.filter(v => v === y).length;
  bands.push(`<g class="band${k ? "" : " empty"}"${k ? ` data-f="year:${y}" tabindex="0" role="button" aria-label="${y}: ${k} incidents"` : ""}><rect x="${X(y)}" y="${T}" width="${X(y + 1) - X(y)}" height="${H - T - B}"/>${k ? `<title>${y}: ${k} incidents</title>` : ""}<text x="${X(y + 0.5)}" y="${H - 6}" text-anchor="middle">${y === y0 || y === y1 || y % 2 === 0 ? y : ""}</text></g>`); }
document.getElementById("chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Cumulative incidents by year, ${y0} to ${y1}">
  ${ticksY.map(n => `<line class="ax" x1="${L}" x2="${W - R}" y1="${Y(n)}" y2="${Y(n)}"/><text x="${L - 8}" y="${Y(n) + 4}" text-anchor="end">${n}</text>`).join("")}
  <path class="ar" d="${d}L${X(y1 + 1)} ${Y(0)}Z"/><path class="ln" d="${d}"/>
  ${bands.join("")}
  <line class="mark" x1="${X(FULL)}" x2="${X(FULL)}" y1="${T - 14}" y2="${H - B}"/>
  <text class="marktx" x="${X(FULL) - 6}" y="${T - 4}" text-anchor="end">Full AIID sourcing from 2024</text>
  <circle cx="${X(y1 + 1)}" cy="${Y(cum)}" r="3.5" fill="var(--ink)"/>
  <text x="${X(y1 + 1) - 8}" y="${Y(cum) + 16}" text-anchor="end" style="fill:var(--ink)">${cum}</text></svg>`;
const before = years.filter(y => y < FULL).length;
document.getElementById("timecap").innerHTML = `<b>Fig. 3</b> Click a year to filter. The axis starts at ${y0}, the year of the earliest incident in the index. ${before} incidents predate ${FULL}, when full AIID sourcing begins; each was flagged or found by hand, so the years before the line are sampled, not screened.`;

// §4 all incidents
const fl = document.getElementById("filters");
fl.innerHTML = [["all", "All"], ...TIERS].map(([t, l]) => `<button class="chip" type="button" id="f-${t}" data-t="${t}" aria-pressed="${t === "all"}">${l} · ${t === "all" ? inc.length : inc.filter(x => x.e === t).length}</button>`).join("");
fl.addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; tierChip = b.dataset.t;
  fl.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); render(); });
const dash = `<span style="color:var(--ink-2)">·</span>`;
// sortable, filterable columns
const VRANK = {verified: 0, partially_verified: 1, unverified: 2};
const COLS = [
  {id: "k", label: "Key", sort: x => x.k, filter: "text", test: (x, q) => x.k.toLowerCase().includes(q)},
  {id: "t", label: "Incident", sort: x => x.t.toLowerCase(), filter: "text", test: (x, q) => x.t.toLowerCase().includes(q)},
  {id: "d", label: "Date", sort: x => x.d, filter: "text", test: (x, q) => x.d.startsWith(q)},
  {id: "fm", label: "FM", sort: x => x.fm || "~", filter: "select",
    opts: [...FMs.map(f => [f.id, `${f.id} ${f.n}`]), ["none", "none"]], test: (x, q) => q === "none" ? !x.fm : x.fm === q},
  {id: "i", label: "Instances", sort: x => x.i.length ? x.i.join(" ") : "~", filter: "select",
    opts: inst.filter(i => nInst(i.id)).map(i => [i.id, `${i.id} ${i.n}`]).concat([["none", "none"]]), test: (x, q) => q === "none" ? !x.i.length : x.i.includes(q)},
  {id: "c", label: "Source", sort: x => SHORT[x.c] || x.c, filter: "select",
    opts: srcIds.map(s => [s, SHORT[s] || s]), test: (x, q) => x.c === q},
  {id: "v", label: "Check", sort: x => VRANK[x.v], filter: "select",
    opts: Object.keys(CHECK).map(k => [k, k.replace("_", " ")]), test: (x, q) => x.v === q},
];
const colq = {};
let sortBy = "d", sortDir = -1;
document.getElementById("thead").innerHTML =
  `<tr>${COLS.map(c => `<th><button type="button" class="sort" data-s="${c.id}" id="s-${c.id}">${c.label}<span class="arr" aria-hidden="true"></span></button></th>`).join("")}</tr>` +
  `<tr class="fr">${COLS.map(c => `<th>${c.filter === "text"
    ? `<input type="search" id="q-${c.id}" data-q="${c.id}" placeholder="${c.id === "d" ? "2025" : "filter"}" aria-label="Filter ${c.label}">`
    : `<select id="q-${c.id}" data-q="${c.id}" aria-label="Filter ${c.label}"><option value="">all</option>${c.opts.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select>`}</th>`).join("")}</tr>`;
const thead = document.getElementById("thead");
thead.addEventListener("click", e => { const b = e.target.closest("button.sort"); if (!b) return;
  if (sortBy === b.dataset.s) sortDir = -sortDir; else { sortBy = b.dataset.s; sortDir = 1; } rows(); });
thead.addEventListener("input", e => { const el = e.target.closest("[data-q]"); if (!el) return; colq[el.dataset.q] = el.value.trim(); rows(); });
const colsActive = () => COLS.filter(c => colq[c.id]);
function rows() {
  const sc = COLS.find(c => c.id === sortBy);
  const list = inc.filter(matches).filter(x => colsActive().every(c => c.test(x, c.filter === "text" ? colq[c.id].toLowerCase() : colq[c.id])))
    .sort((a, b) => { const p = sc.sort(a), q = sc.sort(b); return (p < q ? -1 : p > q ? 1 : 0) * sortDir || b.d.localeCompare(a.d); });
  thead.querySelectorAll("button.sort").forEach(b => { const on = b.dataset.s === sortBy;
    b.classList.toggle("on", on); b.querySelector(".arr").textContent = on ? (sortDir > 0 ? " ↑" : " ↓") : "";
    b.closest("th").setAttribute("aria-sort", on ? (sortDir > 0 ? "ascending" : "descending") : "none"); });
  document.getElementById("rows").innerHTML = list.map(x => `<tr>
      <td class="m">${x.k}</td>
      <td>${tierMark(x.e)}${esc(x.t)}</td>
      <td class="m">${x.d}</td>
      <td class="m">${x.fm ? abbr(x.fm, riskOf[x.fm].n) : dash}</td>
      <td class="m">${x.i.length ? x.i.map(i => abbr(i, instOf[i]?.n || i)).join("") : dash}</td>
      <td class="m"><a href="${esc(x.u)}" title="${esc(srcName(x.c))}">${esc(SHORT[x.c] || x.c)} ↗</a></td>
      <td><span class="vf ${x.v}" title="${esc(CHECK[x.v])}">${x.v.replace("_", " ")}</span></td></tr>`).join("") ||
    `<tr><td colspan="7" class="empty">No incident matches these filters.</td></tr>`;
  const bits = [];
  if (sel) bits.push(esc(parts(sel).map(([k, v]) => DESC[k](v)[0]).join(" × ")));
  if (colsActive().length) bits.push(colsActive().map(c => `${c.label}: ${esc(colq[c.id])}`).join(", "));
  document.getElementById("tblstate").innerHTML = `Showing ${list.length} of ${inc.length}${bits.length ? " · " + bits.join(" · ") : ""}` +
    (sel || colsActive().length ? ` <button type="button" class="chip" id="clear-tbl">Clear filters</button>` : "");
}

// the floating panel; minimised, it docks as a chip in the top bar
const panel = document.getElementById("panel"), barf = document.getElementById("barfilter");
let minimised = false;
function render() {
  document.querySelectorAll("[data-f]").forEach(el => el.classList.toggle("sel", el.dataset.f === sel));
  rows();
  if (!sel) { panel.hidden = true; barf.hidden = true; document.body.classList.remove("docked"); return; }
  const list = inc.filter(x => parts(sel).every(([k, v]) => PRED[k](v)(x)));
  const ps = parts(sel).map(([k, v]) => DESC[k](v));
  const title = ps.map(p => p[0]).join(" × ");
  panel.innerHTML = `<div class="p-head"><span class="lab">Filter</span><span class="p-btns">
      <button type="button" class="x" id="p-min" aria-label="Minimise to the top bar" title="Minimise">–</button>
      <button type="button" class="x" id="p-close" aria-label="Clear filter" title="Clear">×</button></span></div>
    <div class="p-body">
      ${ps.map(([t, dsc]) => `<div class="p-part"><b>${esc(t)}</b><p>${esc(dsc)}</p></div>`).join(`<div class="p-and">and</div>`)}
      <div class="p-count"><span class="v">${list.length}</span> incident${list.length === 1 ? "" : "s"}</div>
      <ul class="p-list">${list.slice(0, 8).map(x => `<li><span class="mono">${x.k}</span> ${esc(x.t)}</li>`).join("")}${list.length > 8 ? `<li class="more">and ${list.length - 8} more</li>` : ""}</ul>
    </div>
    <div class="p-act"><a class="chip" href="#incidents">Show in table</a><button type="button" class="chip" id="p-clear">Clear</button></div>`;
  barf.innerHTML = `<button type="button" class="bf-open" id="bf-open" title="Open the filter window">Filter · <b>${esc(title)}</b> · ${list.length}</button><button type="button" class="bf-x" id="bf-x" aria-label="Clear filter" title="Clear">×</button>`;
  panel.hidden = minimised;
  barf.hidden = !minimised;
  document.body.classList.toggle("docked", minimised);
  if (minimised) { barf.classList.remove("flash"); void barf.offsetWidth; barf.classList.add("flash"); }
}
function pick(key) { sel = sel === key ? null : key; render(); }
document.addEventListener("click", e => {
  if (e.target.closest("#clear-tbl")) { for (const k in colq) delete colq[k]; thead.querySelectorAll("[data-q]").forEach(el => el.value = ""); }
  if (e.target.closest("#p-close, #p-clear, #clear-tbl, #bf-x")) { sel = null; render(); return; }
  if (e.target.closest("#p-min")) { minimised = true; render(); document.getElementById("bf-open")?.focus(); return; }
  if (e.target.closest("#bf-open")) { minimised = false; render(); document.getElementById("p-min")?.focus(); return; }
  const el = e.target.closest("[data-f]"); if (el) pick(el.dataset.f);
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && sel) { sel = null; render(); return; }
  const el = e.target.closest && e.target.closest("[data-f]");
  if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(el.dataset.f); }
});
render();

// §5 data dictionary, one foldable group per kind of code
const dd = (t, d) => `<dt>${t}</dt><dd>${d}</dd>`;
const group = (title, items) => `<details class="sub"><summary><span class="lab">${title}</span><span class="cnt">${items.length}</span></summary><dl class="defs">${items.join("")}</dl></details>`;
document.getElementById("defs").innerHTML =
  group("Columns", [
    dd("Key", "MIG-nnnn, the index's own incident key. Given once, never changed or reused."),
    dd("FM", "The incident's failure mode, derived by rule. Blank when the facts read do not settle it."),
    dd("Instances", "The mechanisms assigned to the incident, each quoted from the source. Each instance sits under the risk where the paper discusses it; that placement gives the incident no label."),
    dd("Source", "Link to the incident in its canonical source.")]) +
  group("Check", Object.entries(CHECK).map(([k, v]) => dd(`<span class="vf ${k}">${k.replace("_", " ")}</span>`, v))) +
  group("Evidence type", TIERS.map(([t]) => dd(`${tierMark(t)}${t}`, TIERDEF[t]))) +
  group("Failure modes · Hammond et al. 2025", FMs.map(r => dd(r.id, `${esc(r.n)}. <span style="color:var(--ink-2)">${esc(r.d)}</span>`))) +
  group("Risk factors · Hammond et al. 2025 · not yet classified", RFs.map(r => dd(r.id, `${esc(r.n)}. <span style="color:var(--ink-2)">${esc(r.d)}</span>`))) +
  group("Instances", inst.map(i => dd(i.id, `${esc(i.n)} <span class="mono" style="font-size:11px">· ${i.r}${i.p === "ours" ? " · ours" : ""}</span>`)));

# generates the method flowchart as inline SVG
from html import escape as e
W = 680; SX, SW = 112, 300; CX = SX + SW // 2; DX, DW = 452, 220
H_N = 50; GAP = 34; PH = 26
nodes = []   # (id, phase, kind, title, sub, side)
spine = [
 ("INGEST", [
  ("fetch", "script", "Fetch AIID", "the AI Incident Database, verbatim"),
  ("norm", "script", "Normalise into records", "one record per source item, hashed")]),
 ("SCREEN", [
  ("pre", "script", "Queue the candidates", "AIID from 2024 · hand-kept older cases"),
  ("read", "model", "Read the sources", "seven facts, each quoted or 'silent'"),
  ("rdy", "script", "Enough read?", "per decision: ready, provisional, not")]),
 ("CLASSIFY", [
  ("c1", "model", "Extract the gate facts", "agents, interaction, cooperation, goals"),
  ("der", "rule", "Derive labels by rule", "Gate 1 scope · Gate 2 failure mode"),
  ("dec", "person", "Decide scope", "in, out or unclear, with a reason"),
  ("c2", "model", "Assign instances", "each match quoted from the source")]),
 ("RECORD", [
  ("prom", "person", "Promote and write the dossier", "unverified until checked by a person"),
  ("idx", "script", "Check, index, report", "the build fails on any broken rule")]),
]
edge_lab = {("fetch","norm"):"raw copy, never edited", ("norm","pre"):"records", ("pre","read"):"queued, some flagged",
  ("read","rdy"):"facts read", ("rdy","c1"):"ready", ("c1","der"):"facts with quotes", ("der","dec"):"in, out or review",
  ("dec","c2"):"decided in", ("c2","prom"):"promote: yes", ("prom","idx"):"dossier"}
pos = {}; y = 64; out = []; phases = []
for ph, items in spine:
    y += PH; top = y - PH + 4
    for (nid, kind, t, s) in items:
        pos[nid] = (y, kind, t, s); y += H_N + GAP
    phases.append((ph, top, y - GAP + 6)); y += 6
H = y - GAP + 24
def box(x, y, w, h, kind, t, s, tid=None):
    r = [f'<g class="fc-{kind}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>']
    r.append(f'<text class="fc-t" x="{x+12}" y="{y+22}">{e(t)}</text>')
    if s: r.append(f'<text class="fc-s" x="{x+12}" y="{y+38}">{e(s)}</text>')
    r.append('</g>'); return "".join(r)
# phase bands
for ph, top, bot in phases:
    out.append(f'<line class="fc-band" x1="0" x2="{W}" y1="{top}" y2="{top}"/><text class="fc-ph" x="0" y="{top+18}">{ph}</text>')
# spine edges
ids = [n for _, it in spine for (n, *_ ) in it]
for a, b in zip(ids, ids[1:]):
    ya = pos[a][0] + H_N; yb = pos[b][0]
    out.append(f'<line class="fc-e" x1="{CX}" y1="{ya}" x2="{CX}" y2="{yb-2}" marker-end="url(#fc-a)"/>')
    out.append(f'<text class="fc-el" x="{CX+10}" y="{(ya+yb)//2+4}">{e(edge_lab[(a,b)])}</text>')
# nodes
for n in ids:
    y0, kind, t, s = pos[n]; out.append(box(SX, y0, SW, H_N, kind, t, s))
# side: manual write-ups join at normalise
yn = pos["norm"][0]; ym = pos["fetch"][0]
out.append(box(DX, ym, DW, H_N, "person", "Curator write-ups", "other sources, fetched by hand"))
out.append(f'<path class="fc-e" d="M{DX+DW//2} {ym+H_N} V{yn+H_N//2} H{SX+SW+2}" marker-end="url(#fc-a)"/>')
out.append(f'<text class="fc-el" x="{DX+DW//2+8}" y="{ym+H_N+18}">added by hand</text>')
# side exits
def exit_(nid, label, sub, dy=0):
    y0 = pos[nid][0] + dy
    out.append(f'<path class="fc-x" d="M{SX+SW} {y0+H_N//2} H{DX-2}" marker-end="url(#fc-ax)"/>')
    out.append(box(DX, y0, DW, H_N, "out", label, sub))
exit_("pre", "Not queued", "pre-2024, or rated single-agent")
exit_("rdy", "Out: one agent or none", "confirmed by a fuller reading")
exit_("dec", "Out or unclear", "logged with the reason")
# loop back: rdy -> read
yr = pos["rdy"][0]; yread = pos["read"][0]
lx = SX - 22
out.append(f'<path class="fc-e" d="M{SX} {yr+H_N//2} H{lx} V{yread+H_N//2} H{SX-2}" marker-end="url(#fc-a)"/>')
out.append(f'<text class="fc-el" x="{lx-4}" y="{(yr+yread)//2+H_N//2+4}" text-anchor="end">read more</text>')
# legend
leg = [("script", "script"), ("model", "model, quotes its source"), ("rule", "fixed rule"), ("person", "person")]
lx0 = 0
for kind, lab in leg:
    out.append(f'<g class="fc-{kind}"><rect x="{lx0}" y="14" width="22" height="14" rx="2"/></g><text class="fc-lg" x="{lx0+30}" y="25">{lab}</text>')
    lx0 += 30 + len(lab) * 7 + 26
defs = ('<defs><marker id="fc-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10 z" class="fc-ah"/></marker>'
        '<marker id="fc-ax" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0 0 L10 5 L0 10 z" class="fc-ahx"/></marker></defs>')
svg = (f'<svg class="fc" viewBox="0 0 {W} {H}" role="img" aria-label="How a record becomes an indexed incident: '
       'fetch and normalise, queue and read the sources, extract facts, derive labels by rule, a person decides scope, '
       'instances are assigned, a person promotes the dossier, then check and index.">' + defs + "".join(out) + '</svg>')
open('flow.svg', 'w').write(svg)
print(W, H)

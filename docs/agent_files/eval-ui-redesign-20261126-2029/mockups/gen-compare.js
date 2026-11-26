const fs = require('fs');
const { ic, chip, th, star, shell } = require('./lib');
const NAME = 'Pilot 4 · AnnoMI gi+persuade';
const combos = {
  A: { m: 'claude-sonnet-4.5', e: 'miti', t: 'standard', f: 'medium', c: 'var(--ca)', shape: 'sq' },
  B: { m: 'gpt-5', e: 'miti', t: 'standard', f: 'high', c: 'var(--cb)', shape: 'tri' },
  C: { m: 'gemini-2.5-pro-preview-long-context', e: 'oneshot:miti', t: 'pro', f: 'high', c: 'var(--cc)', shape: 'ci', failed: true },
  D: { m: 'claude-sonnet-4.5', e: 'oneshot:miti', t: 'standard', f: 'low', c: 'var(--cd)', shape: 'di' },
};
const ok = ['A', 'B', 'D'];
const tag = k => `<span class="tag ${k}">${k}</span>`;
const shapeSvg = (shape, color, x, y, r = 5, extra = '') => ({
  sq: `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" rx="1.5" fill="${color}" ${extra}/>`,
  tri: `<path d="M${x} ${y - r - 1}L${x + r + 1} ${y + r}H${x - r - 1}Z" fill="${color}" ${extra}/>`,
  ci: `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}" ${extra}/>`,
  di: `<path d="M${x} ${y - r - 1}L${x + r + 1} ${y}L${x} ${y + r + 1}L${x - r - 1} ${y}Z" fill="${color}" ${extra}/>`,
}[shape]);
const keyShapes = () => `<div class="keys" aria-hidden="true"><span><svg width="16" height="16"><circle cx="8" cy="8" r="5.5" fill="#fff" stroke="#171c1c" stroke-width="2"/></svg>Human</span>${ok.map(k => `<span><svg width="16" height="16">${shapeSvg(combos[k].shape, combos[k].c, 8, 8, 5)}</svg>${k} ${combos[k].m}</span>`).join('')}</div>`;
const tabsHtml = cur => `<nav class="tabs" role="tablist" aria-label="Compare views">${[['overview', 'Overview'], ['deepdive', 'Deep dive'], ['more', 'More analysis'], ['lines', 'Line view']].map(([f, l]) => `<a href="${f}.html" role="tab" ${f === cur ? 'aria-current="page" aria-selected="true"' : ''}>${l}</a>`).join('')}</nav>`;
const header = cur => `
<div><div class="crumbs"><a href="run.html">Run</a> / Compare</div><h1>Compare - ${NAME}</h1></div>
<section class="card" aria-label="Run summary">
  <div class="sum">
    <div class="stat"><span class="k">Sessions</span><span class="v">5</span><span class="s">2 attempts each · 4 combos</span></div>
    <div class="stat"><span class="k">Human labels</span><div class="chips" style="display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.25rem">${chip('ok', 'check', 'All 10 counts')}${chip('ok', 'check', '4 globals')}</div></div>
    <div class="stat"><span class="k">Coverage</span><div style="display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.25rem">${chip('ok', 'check', 'gi 1/1')}${chip('warn', 'alert', 'persuade 0/1')}${chip('ok', 'check', 's03 1/1')}${chip('ok', 'check', 's04 1/1')}${chip('ok', 'check', 's05 1/1')}</div><span class="s">paired sessions per metric</span></div>
    <div class="stat"><span class="k">Excluded</span><div style="display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.25rem">${chip('err', 'x', 'C: all runs failed')}</div><span class="s">invalid_parameters</span></div>
  </div>
</section>
${tabsHtml(cur)}`;
const legend = `<section class="card" aria-label="Combo legend"><header><h2>Combos</h2></header><div class="legend">${Object.entries(combos).map(([k, c]) => `<div style="${c.failed ? 'background:var(--low-bg);border-color:#efc4c4' : ''}">${tag(k)}<span><b>${c.m}</b>${c.failed ? ' ' + chip('err', 'x', 'failed') : ''}<small>${c.e} · ${c.t} · ${c.f}</small></span></div>`).join('')}</div></section>`;
const write = (f, t, b) => fs.writeFileSync(`${__dirname}/${f}`, shell(t, b));

/* ---------- OVERVIEW ---------- */
const lb = [
  ['A', 3.4, 81, 61, 0.55, 0, 3.2, 41, '10 of 12'], ['B', 3.1, 78, 66, 0.53, 1, 1.1, 18, '11 of 12'], ['D', 4.4, 69, 58, 0.44, 0, 0.7, 25, '12 of 12'],
];
const minOf = i => Math.min(...lb.map(r => r[i])), maxOf = i => Math.max(...lb.map(r => r[i]));
const bestCell = (v, b) => v === b ? star : '';
const lbRows = lb.map(r => `<tr><td data-label="Combo" data-v="${r[0]}"><div class="row" style="flex-wrap:nowrap">${tag(r[0])}<span class="trunc" style="min-width:0"><b>${combos[r[0]].m}</b><span class="sub">${combos[r[0]].e} · ${combos[r[0]].t} · ${combos[r[0]].f}</span></span></div></td>
<td data-label="Count error" data-v="${r[1]}"><b>${r[1].toFixed(1)}</b>${bestCell(r[1], minOf(1))}<span class="sub">${r[8]} paired</span></td>
<td data-label="Globals ±1" data-v="${r[2]}"><b>${r[2]}%</b>${bestCell(r[2], maxOf(2))}</td>
<td data-label="Line accuracy" data-v="${r[3]}"><b>${r[3]}%</b>${bestCell(r[3], maxOf(3))}</td>
<td data-label="Line macro F1" data-v="${r[4]}"><b>${r[4].toFixed(2)}</b>${bestCell(r[4], maxOf(4))}</td>
<td data-label="Fails" data-v="${r[5]}"><b>${r[5]}</b>${bestCell(r[5], minOf(5))}</td>
<td data-label="Cost" data-v="${r[6]}"><b>$${r[6].toFixed(2)}</b>${bestCell(r[6], minOf(6))}</td>
<td data-label="Time" data-v="${r[7]}"><b>${r[7]}m</b>${bestCell(r[7], minOf(7))}</td></tr>`).join('') +
  `<tr class="fail"><td data-label="Combo" data-v="C"><div class="row" style="flex-wrap:nowrap">${tag('C')}<span style="min-width:0"><b>${combos.C.m}</b><span class="sub">${combos.C.e} · ${combos.C.t} · ${combos.C.f}</span></span></div></td><td data-label="Status" colspan="7">${chip('err', 'x', 'Failed · invalid_parameters')} <span class="muted" style="font-size:.8rem">2 of 2 runs failed. Excluded from rankings and "best".</span></td></tr>`;

const hmRows = [
  ['Behavior counts (lines)'],
  ['Giving Information', 18, [[1.2, 1.0], [.8, -.6], [2.0, 2.0]]], ['Persuade', 2, [[.4, .4], [.6, .6], [1.2, 1.2]]], ['Persuade w/ Permission', 3, [[.8, -.8], [.4, -.2], [1.0, -1.0]]],
  ['Question', 24, [[2.1, -2.1], [.4, -.4], [1.8, -1.8]]], ['Simple Reflection', 9, [[.9, .9], [1.2, 1.2], [.3, .3]]], ['Complex Reflection', 11, [[1.5, -1.5], [.8, -.8], [.2, -.2]]],
  ['Affirm', 3, [[.5, .5], [.7, .7], [1.4, 1.4]]], ['Seek Collaboration', 2, [[.3, .1], [.5, .5], [.8, -.8]]], ['Emphasize Autonomy', 2, [[.2, .2], [.2, -.2], [.6, -.6]]], ['Confront', 0, [[0, 0], [0, 0], [.4, .4]]],
  ['Globals (1-5 points)'],
  ['Cultivating Change Talk', '3.6', [[.6, .4], [.4, -.2], [.8, .4]], 'pt'], ['Softening Sustain Talk', '3.0', [[.8, .4], [.6, -.6], [1.0, .6]], 'pt'], ['Partnership', '4.0', [[.4, .2], [.6, .6], [.8, -.4]], 'pt'], ['Empathy', '4.2', [[.4, .2], [.2, .2], [.6, -.6]], 'pt'],
  ['Ratios'],
  ['R:Q', '0.83', [[.30, -.3], [.12, -.1], [.21, .2]], 'ratio'], ['%CR', '55%', [[9, -9], [6, 6], [4, 4]], 'ratio'],
];
const cls = (off, kind) => kind === 'pt' ? (off <= .4 ? 'g' : off <= .7 ? 'n' : 'a') : kind === 'ratio' ? 'n' : (off <= .6 ? 'g' : off <= 1.0 ? 'n' : off <= 1.8 ? 'a' : 'r');
const sg = v => (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v);
const hm = hmRows.map(r => {
  if (r.length === 1) return `<tr class="grp"><td colspan="6">${r[0]}</td></tr>`;
  const [label, human, vals, kind] = r; const min = Math.min(...vals.map(v => v[0]));
  return `<tr><td>${label}</td><td><b>${human}</b></td>${vals.map(([off, bias]) => `<td class="${cls(off, kind)} ${off === min ? 'bst' : ''}"><span class="big">${off}</span><span class="sm">${sg(bias)}</span></td>`).join('').replace(/(<td[^>]*>.*?<\/td>)(<td[^>]*>.*?<\/td>)(<td[^>]*>.*?<\/td>)/, '$1$2<td class="fx" title="C: all runs failed">failed</td>$3')}</tr>`;
}).join('');
// column order: Human, A, B, C, D
const overview = `${header('overview')}
<section class="card verdict"><header><h2>Verdict</h2></header>
<p><b>B is closest to human on counts</b> <span class="chip zero">n=11</span>, <b>A is best on global ratings</b> <span class="chip zero">n=10</span>. All combos under-count Questions.</p>
<p class="note">Combo C is excluded: every run failed with invalid_parameters.</p></section>
${legend}
<section class="card"><header><div><h2>Leaderboard</h2><p class="note" style="margin:0">Default sort: Count error, lowest first. Click a header arrow to sort.</p></div></header>
<table class="stack" data-table="lb"><colgroup><col style="width:25%"><col style="width:12%"><col style="width:11%"><col style="width:12%"><col style="width:12%"><col style="width:8%"><col style="width:10%"><col style="width:10%"></colgroup>
<thead><tr>${th('Combo')}${th('Count error')}${th('Globals ±1')}${th('Line accuracy')}${th('Line macro F1')}${th('Fails')}${th('Cost')}${th('Time')}</tr></thead><tbody>${lbRows}</tbody></table>
<div class="keys"><span><svg style="width:.9rem;color:var(--fair)" viewBox="0 0 16 16">${ic.star.replace(/<\/?svg[^>]*>/g, '')}</svg> best in column</span><span><span class="sw" style="background:var(--low-bg)"></span>failed combo, excluded</span></div>
<p class="note"><b>Count error</b>: average tallies missed per session across 10 codes. <b>Globals ±1</b>: ratings within one point of human. <b>Cost/Time</b>: operational, not compared with human. Sessions have equal weight; repeats are averaged inside each session first.</p>
<p class="note">Time is finished minus started per unit; started resets on re-claim, so retried units can read short.</p></section>
<section class="card"><header><div><h2>Metric heatmap</h2><p class="note" style="margin:0">Big number: average miss vs human. Small: signed bias (+ over-counts, − under-counts).</p></div></header>
<table class="hm" style="table-layout:fixed"><colgroup><col style="width:30%"><col style="width:11%"><col style="width:15%"><col style="width:15%"><col style="width:14%"><col style="width:15%"></colgroup>
<thead><tr><th scope="col">Metric</th><th scope="col">Human</th><th scope="col">${tag('A')}</th><th scope="col">${tag('B')}</th><th scope="col">${tag('C')}</th><th scope="col">${tag('D')}</th></tr></thead><tbody>${hm}</tbody></table>
<div class="keys"><span><span class="sw" style="background:var(--good-bg)"></span>within tolerance (0.6 lines / 0.4 points)</span><span><span class="sw" style="background:#fff"></span>close</span><span><span class="sw" style="background:var(--fair-bg)"></span>off</span><span><span class="sw" style="background:var(--low-bg)"></span>far off</span><span><span class="sw" style="outline:2px solid var(--fair);outline-offset:-2px"></span>best in row</span></div>
<p class="note">Ratios (R:Q, %CR) have no tolerance, so never green. Click a cell to open it in Deep dive. Colour shows size only; the sign is always printed.</p></section>`;
write('overview.html', 'Compare Overview', overview);

/* ---------- DEEP DIVE ---------- */
const sess = ['gi', 'persuade', 's03', 's04', 's05'];
function dotPlot(title, human, series) {
  const W = 640, gx = 150, px = 20, rowH = 58, top = 34, H = top + rowH * sess.length + 8, X = v => gx + (v - 1) / 4 * (W - gx - px);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}: human and combo ratings per interview">`;
  for (let v = 1; v <= 5; v++) s += `<line x1="${X(v)}" x2="${X(v)}" y1="${top - 8}" y2="${H - 8}" stroke="#d3dbda" stroke-dasharray="${v === 1 || v === 5 ? '0' : '3 4'}"/><text x="${X(v)}" y="${top - 16}" text-anchor="middle" font-size="12" fill="#536160">${v}</text>`;
  sess.forEach((name, i) => {
    const cy = top + i * rowH + rowH / 2;
    if (i % 2 === 0) s += `<rect x="0" y="${cy - rowH / 2}" width="${W}" height="${rowH}" fill="#f7f9f9" opacity=".7"/>`;
    s += `<text x="8" y="${cy + 4}" font-size="13" font-weight="600" fill="#171c1c">${name}</text>`;
    const lanes = [['H', -18], ['A', -6], ['B', 6], ['D', 18]];
    s += `<line x1="${X(human[i])}" x2="${X(human[i])}" y1="${cy - 24}" y2="${cy + 24}" stroke="#171c1c" stroke-opacity=".35" stroke-dasharray="2 3"/>`;
    lanes.forEach(([k, dy]) => { if (k === 'H') s += `<circle cx="${X(human[i])}" cy="${cy + dy}" r="5.5" fill="#fff" stroke="#171c1c" stroke-width="2"/>`; else s += shapeSvg(combos[k].shape, combos[k].c, X(series[k][i]), cy + dy, 4.5); });
  });
  return s + '</svg>';
}
const missStats = (human, series) => ok.map(k => { const d = series[k].map((v, i) => Math.abs(v - human[i])); const avg = d.reduce((a, b) => a + b, 0) / d.length; const w = d.filter(x => x <= 1).length / d.length; return { k, avg, w, buckets: [d.filter(x => x === 0).length, d.filter(x => x === 1).length, d.filter(x => x >= 2).length] }; });
const g1 = { h: [4, 3, 2, 4, 3], s: { A: [4, 3, 3, 4, 2], B: [4, 2, 2, 5, 3], D: [3, 3, 2, 3, 4] } };
const g2 = { h: [3, 4, 4, 5, 4], s: { A: [3, 4, 4, 4, 4], B: [4, 4, 3, 5, 5], D: [2, 4, 4, 3, 4] } };
function stacked(stats) {
  const W = 640, rows = stats.length, H = rows * 34 + 6; let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Share of ratings exactly matching, off by one, or off by two or more">`;
  stats.forEach((st, i) => {
    const y = 4 + i * 34, bx = 36, bw = 430, tot = 5; let x = bx;
    s += `<g transform="translate(0,${y})"><rect x="0" y="2" width="22" height="22" rx="4" fill="${combos[st.k].c}"/><text x="11" y="18" text-anchor="middle" font-size="13" font-weight="700" fill="#fff">${st.k}</text>`;
    [['#2f8f68', 'same'], ['#e0a93b', '±1'], ['#c25b5b', '2+']].forEach(([c, l], j) => { const w = st.buckets[j] / tot * bw; if (w > 0) { s += `<rect x="${x}" y="2" width="${w - 1}" height="22" fill="${c}"/><text x="${x + w / 2}" y="18" text-anchor="middle" font-size="11.5" font-weight="650" fill="#fff">${st.buckets[j]}</text>`; } x += w; });
    s += `<text x="${bx + bw + 14}" y="12" font-size="12" fill="#171c1c" font-weight="600">miss ${st.avg.toFixed(1)}</text><text x="${bx + bw + 14}" y="25" font-size="11" fill="#536160">within ±1: ${Math.round(st.w * 100)}%</text></g>`;
  });
  return s + '</svg>';
}
const lineLeg = `<div class="keys" aria-hidden="true"><span><span class="sw" style="background:#2f8f68"></span>same</span><span><span class="sw" style="background:#e0a93b"></span>off by 1</span><span><span class="sw" style="background:#c25b5b"></span>off by 2+</span></div>`;
function hbars(code, vals) {
  const W = 300, labelX = 24, bx = 30, bw = 190, max = Math.max(...vals.map(v => v[1]), 1), H = vals.length * 24 + 6;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${code} total counts by source">`;
  vals.forEach(([k, v], i) => { const y = 3 + i * 24, c = k === 'H' ? '#171c1c' : combos[k].c; s += `<text x="${labelX - 6}" y="${y + 14}" text-anchor="end" font-size="12" font-weight="700" fill="${c}">${k}</text><rect x="${bx}" y="${y + 2}" width="${Math.max(v / max * bw, 2)}" height="16" rx="3" fill="${c}" ${k === 'H' ? 'fill-opacity=".85"' : ''}/><text x="${bx + v / max * bw + 6}" y="${y + 15}" font-size="12" fill="#171c1c" font-variant-numeric="tabular-nums">${v}</text>`; });
  return s + '</svg>';
}
const counts = [['Questions', [['H', 118], ['A', 93], ['B', 112], ['D', 96]], [['A', 'under', 21, 'err'], ['B', 'close', 5, 'ok'], ['D', 'under', 19, 'err']]],
['Simple Reflection', [['H', 44], ['A', 49], ['B', 53], ['D', 45]], [['A', 'over', 11, 'warn'], ['B', 'over', 20, 'warn'], ['D', 'close', 2, 'ok']]],
['Complex Reflection', [['H', 52], ['A', 44], ['B', 48], ['D', 51]], [['A', 'under', 15, 'warn'], ['B', 'under', 8, 'ok'], ['D', 'close', 2, 'ok']]],
['Giving Information', [['H', 86], ['A', 95], ['B', 80], ['D', 104]], [['A', 'over', 10, 'warn'], ['B', 'under', 7, 'ok'], ['D', 'over', 21, 'err']]]];
const prfRows = [['Question', [[.92, .90, .91], [.95, .93, .94], [.86, .82, .84]]], ['Simple Reflection', [[.70, .64, .67], [.62, .69, .65], [.74, .70, .72]]], ['Complex Reflection', [[.48, .39, .43], [.58, .55, .56], [.61, .60, .60]]], ['Giving Information', [[.78, .81, .79], [.80, .74, .77], [.66, .83, .73]]], ['Affirm', [[.55, .50, .52], [.60, .50, .55], [.40, .67, .50]]]];
const bar = (v, c) => `<span style="display:inline-block;height:.55rem;width:${Math.round(v * 70)}px;max-width:60%;background:${c};border-radius:3px;vertical-align:middle;margin-right:.4rem"></span>`;
const prf = prfRows.map(([code, vals]) => `<tr><td data-label="Code"><b>${code}</b></td>${vals.map((v, i) => `<td data-label="${ok[i]} (P / R / F1)">${bar(v[2], combos[ok[i]].c)}<b>${v[2].toFixed(2)}</b><span class="sub">P ${v[0].toFixed(2)} · R ${v[1].toFixed(2)}</span></td>`).join('')}</tr>`).join('');
const conf = [[40, 1, 0, 0, 3, 0], [2, 22, 9, 0, 4, 1], [0, 14, 11, 1, 5, 0], [1, 0, 2, 17, 2, 0], [4, 3, 5, 6, '—', 0]];
const cl = ['Q', 'SR', 'CR', 'GI', 'none', 'multi'];
const confHtml = conf.map((r, i) => `<tr><th scope="row" style="background:var(--muted);text-align:left">Human ${cl[i]}</th>${r.map((v, j) => { const diag = i === j; const a = typeof v === 'number' ? Math.min(v / 40, 1) : 0; return `<td style="text-align:center;font-weight:${diag ? 700 : 500};background:${diag ? `rgba(23,91,66,${.12 + a * .55})` : v > 0 ? `rgba(180,83,9,${a * .8 + .06})` : 'transparent'};color:${(diag && a > .5) ? '#fff' : 'inherit'}" ${v === 14 ? 'title="B called 14 CR lines SR"' : ''}>${v}${v === 14 ? '<span class="sr"> hot spot</span>' : ''}</td>`; }).join('')}</tr>`).join('');
const stats1 = missStats(g1.h, g1.s), stats2 = missStats(g2.h, g2.s);
const deep = `${header('deepdive')}
<section class="card"><header><div><h2>Compare combos</h2><p class="note" style="margin:0">Human is always shown. Top 3 by Count error selected by default.</p></div><span class="chip zero">paired 5 of 5 sessions</span></header>
<div class="seg" role="group" aria-label="Combos to compare">${['A', 'B', 'D'].map(k => `<button aria-pressed="true">${k} · ${combos[k].m} · ${combos[k].f}</button>`).join('')}<button aria-pressed="false" disabled title="All runs failed">C · failed, unavailable</button></div></section>
<h2 style="margin-top:.5rem">Globals</h2>
<div class="grid2">
<section class="card"><header><h3>Cultivating Change Talk</h3></header><figure>${dotPlot('Cultivating Change Talk', g1.h, g1.s)}<figcaption>Rating 1-5 per interview. Hollow circle = human; shapes = combos. Dashed line marks the human rating.</figcaption></figure>${keyShapes()}
<div class="row" style="margin-top:.6rem">${stats1.map(s => chip('neutral', '', `<b>${s.k}</b> miss ${s.avg.toFixed(1)} · ±1 ${Math.round(s.w * 100)}%`)).join('')}</div></section>
<section class="card"><header><h3>Partnership</h3></header><figure>${dotPlot('Partnership', g2.h, g2.s)}<figcaption>Same scale and symbols.</figcaption></figure>${keyShapes()}
<div class="row" style="margin-top:.6rem">${stats2.map(s => chip('neutral', '', `<b>${s.k}</b> miss ${s.avg.toFixed(1)} · ±1 ${Math.round(s.w * 100)}%`)).join('')}</div></section></div>
<section class="card"><header><h3>How far off are the ratings?</h3><span class="muted" style="font-size:.8rem">Cultivating Change Talk · interviews per bucket</span></header><figure>${stacked(stats1)}</figure>${lineLeg}</section>
<h2>Counts per code</h2>
<div class="grid2">${counts.map(([code, vals, bias]) => `<section class="card"><header><h3>${code}</h3></header><figure>${hbars(code, vals)}</figure><div class="row" style="margin-top:.4rem">${bias.map(([k, w, p, c]) => chip(c, c === 'ok' ? 'check' : 'alert', `${k} ${w === 'close' ? 'close' : w + '-counts'} ${w === 'close' ? '' : p + '%'}`)).join('')}</div></section>`).join('')}</div>
<p class="note">Counts are totals over the 5 paired sessions. Bias chips: green within 10%, amber 10-20%, red over 20%.</p>
<h2>Per-line agreement</h2>
<div class="grid2" style="align-items:start">
<section class="card"><header><div><h3>Precision / recall / F1</h3><p class="note" style="margin:0">5 of 10 codes labeled in this dataset.</p></div></header>
<table class="stack"><thead><tr>${th('Code', false)}${ok.map(k => th(k + ' · F1', false)).join('')}</tr></thead><tbody>${prf}</tbody></table>
<p class="note">Precision: when the combo says X, how often human agreed. Recall: of human's X lines, how many it found. F1 is low if either is low.</p></section>
<section class="card"><header><div><h3>Confusion · combo B</h3><p class="note" style="margin:0">Rows: human code. Columns: B's code.</p></div><div class="seg" role="group" aria-label="Combo"><button aria-pressed="false">A</button><button aria-pressed="true">B</button><button aria-pressed="false">D</button></div></header>
<table style="table-layout:fixed;text-align:center"><thead><tr><th scope="col" style="background:var(--muted)"></th>${cl.map(c => `<th scope="col" style="text-align:center">${c}</th>`).join('')}</tr></thead><tbody>${confHtml}</tbody></table>
<div class="keys"><span><span class="sw" style="background:rgba(23,91,66,.5)"></span>agree</span><span><span class="sw" style="background:rgba(180,83,9,.5)"></span>confused (click to see lines)</span></div>
<p class="note">B called 14 CR lines SR. Multi-code lines are kept in their own column so totals match.</p></section></div>
<h2>Reasoning roll-up</h2>
<section class="card">${['Complex Reflection', 'Question'].map((c, i) => `<details ${i === 0 ? 'open' : ''}><summary>${c}</summary><div class="grid3">${['H', 'A', 'B'].map(k => `<div class="stat" style="background:#fff"><span class="k">${k === 'H' ? 'Human' : 'Combo ' + k}</span><span class="v">${k === 'H' ? 52 : k === 'A' ? 44 : 48} lines</span>${k === 'H' ? '<span class="s">1 gold note</span>' : '<div class="quote">Sample rationale text (loaded on demand, shown verbatim).</div>'}</div>`).join('')}</div></details>`).join('')}<p class="note">Snippets load on request, 50 per page. Empty saved reasoning shows as "withheld".</p></section>`;
write('deepdive.html', 'Compare Deep dive', deep);

/* ---------- MORE ANALYSIS ---------- */
function scatter() {
  const W = 640, H = 330, L = 56, R = 20, T = 16, B = 46, X = v => L + v / 3.6 * (W - L - R), Y = v => H - B - (v - 2) / 3 * (H - T - B);
  const pts = [['A', 3.2, 3.4], ['B', 1.1, 3.1], ['D', .7, 4.4]];
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cost per run versus Count error">`;
  [2, 3, 4, 5].forEach(v => s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#d3dbda" stroke-dasharray="3 4"/><text x="${L - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="12" fill="#536160">${v}</text>`);
  [0, 1, 2, 3].forEach(v => s += `<line x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H - B}" stroke="#eef2f2"/><text x="${X(v)}" y="${H - B + 18}" text-anchor="middle" font-size="12" fill="#536160">$${v}</text>`);
  s += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle" font-size="12" fill="#536160">Cost per run (lower is better)</text><text transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="#536160">Count error (lower is better)</text>`;
  s += `<path d="M${X(.7)} ${Y(4.4)}H${X(1.1)}V${Y(3.1)}" fill="none" stroke="#0b5f5a" stroke-width="2" stroke-dasharray="6 4"/><text x="${X(1.25)}" y="${Y(3.1) + 22}" font-size="11" fill="#0b5f5a" font-weight="600">efficient frontier</text>`;
  pts.forEach(([k, x, y]) => { s += shapeSvg(combos[k].shape, combos[k].c, X(x), Y(y), 8) + `<text x="${X(x) + 14}" y="${Y(y) + 4}" font-size="13" font-weight="700" fill="${combos[k].c}">${k}</text>`; });
  return s + '</svg>';
}
function lenScatter() {
  const W = 640, H = 280, L = 56, R = 20, T = 14, B = 44, X = v => L + (v - 60) / 140 * (W - L - R), Y = v => H - B - (v) / 7 * (H - T - B);
  const data = { A: [[80, 2.1], [96, 2.6], [120, 3.2], [150, 4.4], [180, 4.9]], B: [[80, 1.8], [96, 2.2], [120, 2.9], [150, 3.6], [180, 4.1]], D: [[80, 3.1], [96, 3.6], [120, 4.2], [150, 5.4], [180, 6.2]] };
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Count error versus interview length in turns">`;
  [0, 2, 4, 6].forEach(v => s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#d3dbda" stroke-dasharray="3 4"/><text x="${L - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="12" fill="#536160">${v}</text>`);
  [60, 100, 140, 180].forEach(v => s += `<text x="${X(v)}" y="${H - B + 18}" text-anchor="middle" font-size="12" fill="#536160">${v}</text>`);
  s += `<text x="${(L + W - R) / 2}" y="${H - 6}" text-anchor="middle" font-size="12" fill="#536160">Interview length (turns)</text><text transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="#536160">Count error</text>`;
  Object.entries(data).forEach(([k, pts]) => { s += `<polyline points="${pts.map(p => `${X(p[0])},${Y(p[1])}`).join(' ')}" fill="none" stroke="${combos[k].c}" stroke-opacity=".35" stroke-width="2"/>`; pts.forEach(p => s += shapeSvg(combos[k].shape, combos[k].c, X(p[0]), Y(p[1]), 5)); });
  return s + '</svg>';
}
const gridData = [['gi', [3.0, 2.1, 5.2]], ['persuade', [4.1, 3.8, 4.0]], ['s03', [2.8, 3.2, 4.6]], ['s04', [3.9, 3.0, 4.9]], ['s05', [3.2, 3.4, 3.3]]];
const errCell = v => { const c = v <= 3 ? 'var(--good-bg)' : v <= 4 ? '#fff' : v <= 4.7 ? 'var(--fair-bg)' : 'var(--low-bg)'; return c; };
const h2h = { A: { B: '1 of 5', D: '3 of 5' }, B: { A: '4 of 5', D: '4 of 5' }, D: { A: '2 of 5', B: '1 of 5' } };
const more = `${header('more')}
<div class="grid2">
<section class="card"><header><div><h2>Cost vs accuracy</h2><p class="note" style="margin:0">Best combos are bottom-left.</p></div></header><figure>${scatter()}<figcaption>The dashed line joins combos nothing else beats on both axes (D then B). A is costlier than B and less accurate.</figcaption></figure>${keyShapes()}<p class="note">Unpriced combos are not plotted: <b>C</b> (no completed runs).</p></section>
<section class="card"><header><div><h2>Error vs interview length</h2><p class="note" style="margin:0">One point per session and combo.</p></div><div class="seg" role="group" aria-label="Length unit"><button aria-pressed="true">Turns</button><button aria-pressed="false">Words</button></div></header><figure>${lenScatter()}</figure>${keyShapes()}<p class="note">Longer interviews raise error for every combo; D grows fastest.</p></section></div>
<div class="grid2">
<section class="card"><header><h2>Human-vs-human baseline</h2></header><div class="stat" style="background:var(--muted)"><span class="k">Inter-rater agreement</span><span class="v na" style="font-weight:600">n/a</span><span class="s">Needs a second human coder, which is not in this dataset.</span></div></section>
<section class="card"><header><h2>Reliability</h2></header><table class="stack"><thead><tr>${th('Combo', false)}${th('Same MITI level (repeats)', false)}${th('Fails', false)}${th('Time', false)}</tr></thead><tbody>${[['A', '84%', '0', '41m'], ['B', '79%', '1', '18m'], ['D', '71%', '0', '25m']].map(r => `<tr><td data-label="Combo">${tag(r[0])}</td><td data-label="Repeat agreement"><b>${r[1]}</b></td><td data-label="Fails">${r[2]}</td><td data-label="Time">${r[3]}</td></tr>`).join('')}<tr class="fail"><td data-label="Combo">${tag('C')}</td><td colspan="3" data-label="Status">${chip('err', 'x', 'No completed runs')}</td></tr></tbody></table></section></div>
<div class="grid2" style="align-items:start">
<section class="card"><header><div><h2>Head-to-head</h2><p class="note" style="margin:0">Row combo closer to human than column combo, on N of 5 sessions.</p></div></header>
<table style="table-layout:fixed;text-align:center"><thead><tr><th scope="col" style="background:var(--muted)">closer ↓ / than →</th>${ok.map(k => `<th scope="col" style="text-align:center">${tag(k)}</th>`).join('')}</tr></thead><tbody>${ok.map(r => `<tr><th scope="row" style="background:var(--muted);text-align:left">${tag(r)}</th>${ok.map(c => r === c ? '<td style="background:var(--secondary)">—</td>' : `<td style="background:${parseInt(h2h[r][c]) >= 4 ? 'var(--good-bg)' : parseInt(h2h[r][c]) <= 1 ? 'var(--low-bg)' : '#fff'}"><b>${h2h[r][c]}</b></td>`).join('')}</tr>`).join('')}</tbody></table><p class="note">Ties are counted for neither combo.</p></section>
<section class="card"><header><div><h2>Interviews by combo</h2><p class="note" style="margin:0">Count error per session (repeats averaged). Click a session for its Line view.</p></div></header>
<table style="table-layout:fixed;text-align:center"><thead><tr><th scope="col" style="background:var(--muted);text-align:left">Session</th>${ok.map(k => `<th scope="col" style="text-align:center">${tag(k)}</th>`).join('')}</tr></thead><tbody>${gridData.map(([s, v]) => `<tr><th scope="row" style="text-align:left;background:var(--muted)"><a href="lines.html">${s}</a></th>${[0, 1, 2].map(i => `<td style="background:${errCell(v[i])}"><b>${v[i].toFixed(1)}</b><span class="sub">2 repeats</span></td>`).join('')}</tr>`).join('')}</tbody></table>
<div class="keys"><span><span class="sw" style="background:var(--good-bg)"></span>≤3</span><span><span class="sw"></span>3-4</span><span><span class="sw" style="background:var(--fair-bg)"></span>4-4.7</span><span><span class="sw" style="background:var(--low-bg)"></span>&gt;4.7</span></div></section></div>`;
write('more.html', 'Compare More analysis', more);

/* ---------- LINE VIEW ---------- */
const lines = [
  [11, 'Therapist', 'What would you like to be different about your drinking?', 'Q', { A: 'Q', B: 'Q', D: 'Q' }],
  [12, 'Client', 'I guess I just want to feel less guilty in the mornings.', null, { A: null, B: null, D: null }],
  [13, 'Therapist', 'The guilt is weighing on you.', 'SR', { A: 'SR', B: 'CR', D: 'SR' }],
  [14, 'Therapist', 'You want mornings that feel like you, and drinking is getting in the way of that.', 'CR', { A: 'SR', B: 'CR', D: 'SR' }],
  [15, 'Client', 'Yeah. I do not want to stop completely though.', null, {}],
  [16, 'Therapist', 'It is your decision how much to change, and you have been thinking hard about it.', 'AF', { A: 'AF', B: 'AF', D: 'EA' }],
  [17, 'Therapist', 'Would it be okay if I shared what some people find helpful?', 'SC', { A: 'SC', B: 'SC', D: 'PP' }],
  [18, 'Therapist', 'Most people who cut down see their sleep improve first.', 'GI', { A: 'GI', B: 'GI', D: 'GI' }],
];
const lineRows = lines.map(([n, sp, tx, h, c]) => { const dis = h && ok.some(k => c[k] !== h); return `<tr class="${dis ? 'dis' : ''}"><td data-label="#" data-v="${n}">${n}</td><td data-label="Speaker">${sp === 'Therapist' ? chip('info', '', 'Therapist') : chip('neutral', '', 'Client')}</td><td data-label="Line">${tx}</td><td data-label="Human">${h ? `<span class="code">${h}</span>` : ''}</td>${ok.map(k => `<td data-label="${k}">${c[k] ? `<span class="code ${c[k] !== h ? 'x' : ''}">${c[k] !== h ? '⚠ ' : ''}${c[k]}</span>` : ''}</td>`).join('')}</tr>`; }).join('');
const gl = [['Cultivating Change Talk', 4, [4, 4, 3]], ['Softening Sustain Talk', 3, [3, 2, 3]], ['Partnership', 4, [4, 5, 2]], ['Empathy', 4, [4, 4, 4]]];
const rate = (v, h) => `<span class="chip ${v === h ? 'ok' : Math.abs(v - h) === 1 ? 'warn' : 'err'}">${v}${v === h ? '' : ` (${v > h ? '+' : '−'}${Math.abs(v - h)})`}</span>`;
const lv = `${header('lines')}
<section class="card"><header><div><h2>Session</h2></div></header><div class="toolbar"><label>Session <select aria-label="Session"><option>persuade (most matching lines: 31)</option><option>gi</option><option>s03</option></select></label>
<label class="row" style="gap:.4rem"><input type="checkbox" checked> Only disagreements</label><label>Code <select aria-label="Code"><option>all</option><option>SR</option><option>CR</option></select></label><label>Combo <select aria-label="Combo"><option>all</option><option>A</option><option>B</option><option>D</option></select></label>
<span class="chip warn" style="margin-left:auto">${ic.alert}3 lines differ</span></div>
<table class="stack"><colgroup><col style="width:5%"><col style="width:11%"><col style="width:43%"><col style="width:10%"><col style="width:10%"><col style="width:10%"><col style="width:10%"></colgroup><thead><tr>${th('#')}${th('Speaker', false)}${th('Line text', false)}${th('Human', false)}${th('A', false)}${th('B', false)}${th('D', false)}</tr></thead><tbody>${lineRows}</tbody></table>
<p class="note">Amber rows and ⚠ mark disagreements with human. Click a row to see each combo's rationale and "k of r repeats agree". Line text is shown exactly as saved. A blank human cell means no label.</p></section>
<section class="card"><header><div><h2>Global ratings · persuade</h2><p class="note" style="margin:0">Human vs each combo. Green: exact. Amber: off by 1. Red: off by 2+.</p></div></header>
<table class="stack"><thead><tr>${th('Global', false)}${th('Human', false)}${ok.map(k => th(k, false)).join('')}</tr></thead><tbody>${gl.map(([g, h, v]) => `<tr><td data-label="Global"><b>${g}</b></td><td data-label="Human"><span class="chip neutral">${h}</span></td>${v.map((x, i) => `<td data-label="${ok[i]}">${rate(x, h)}</td>`).join('')}</tr>`).join('')}</tbody></table>
<details><summary>Combo A reasoning · Partnership</summary><div class="quote">Sample reasoning text, verbatim from the saved report. Evidence: lines 14, 16.</div></details></section>`;
write('lines.html', 'Compare Line view', lv);

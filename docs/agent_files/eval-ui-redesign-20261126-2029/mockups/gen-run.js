const fs = require('fs');
const { ic, chip, th, shell, modal } = require('./lib');
const RUN_ID = 'run_7f3a91c2e8b4';
const units = [
  ['u-0001', 'gi', 'miti', 'claude-sonnet-4.5', 'standard', 'medium', '1 / 2', 'done', 'complete'],
  ['u-0002', 'gi', 'miti', 'claude-sonnet-4.5', 'standard', 'medium', '2 / 2', 'done', 'complete'],
  ['u-0003', 'gi', 'miti', 'gpt-5', 'standard', 'high', '1 / 2', 'running', 'coding turns 41/96'],
  ['u-0004', 'gi', 'oneshot:miti', 'gemini-2.5-pro-preview-long-context', 'pro', 'high', '1 / 2', 'failed', 'validate request'],
  ['u-0005', 'persuade', 'miti', 'claude-sonnet-4.5', 'standard', 'medium', '1 / 2', 'done', 'complete'],
  ['u-0006', 'persuade', 'miti', 'gpt-5', 'standard', 'high', '1 / 2', 'queued', '—'],
  ['u-0007', 'persuade', 'oneshot:miti', 'gemini-2.5-pro-preview-long-context', 'pro', 'high', '1 / 2', 'queued', '—'],
  ['u-0008', 'gi', 'human', 'human reference', '—', '—', 'Once', 'done', 'complete'],
];
const stChip = { done: chip('ok', 'check', 'Done'), running: chip('info', 'spin', 'Running'), queued: chip('neutral', 'clock', 'Queued'), failed: chip('err', 'x', 'Failed') };
const errText = `{
  "code": "invalid_parameters",
  "message": "Request rejected by provider: 'reasoning_effort' value 'high' is not supported for model 'gemini-2.5-pro-preview-long-context' with tier 'pro'. Supported values: low, medium.",
  "stage": "validate request",
  "provider": "google",
  "http_status": 400,
  "attempt": 1,
  "retryable": false,
  "occurred_at": "2026-11-26T09:41:07Z"
}`;
const result = u => {
  const [id, , , , , , , st] = u;
  if (st === 'done') return `<button class="btn sm" data-open="json-${id}">${ic.copy.replace(/<svg/, '<svg aria-hidden="true"')}View JSON</button>`;
  if (st === 'failed') return `<button class="chip err" style="cursor:pointer;font:inherit;font-size:.8125rem" data-open="error-modal" aria-label="Show full error for ${id}">${ic.alert}invalid_parameters</button>`;
  if (st === 'running') return `<div class="progress" style="width:100%" aria-label="43% through coding"><i class="r" style="width:43%"></i></div>`;
  return '<span class="na">—</span>';
};
const rows = units.map(u => {
  const [id, s, e, m, t, ef, at, st, stage] = u;
  return `<tr data-status="${st}" class="${st === 'failed' ? 'fail' : ''}"><td data-label="Session" class="trunc" title="${s}"><b>${s}</b></td><td data-label="Engine"><span class="chip neutral mono">${e}</span></td><td data-label="Model" class="trunc" title="${m}">${m}</td><td data-label="Tier">${t}</td><td data-label="Effort">${ef}</td><td data-label="Attempt" data-v="${at}">${at}</td><td data-label="Status" data-v="${st}">${stChip[st]}</td><td data-label="Stage" class="trunc" title="${stage}">${stage}</td><td data-label="Result">${result(u)}</td></tr>`;
}).join('');
const cols = ['Session', 'Engine', 'Model', 'Tier', 'Effort', 'Attempt', 'Status', 'Stage'].map(l => th(l)).join('') + th('Result', false);
const widths = ['9%', '12%','18%','7%','8%', '8%', '11%', '12%', '15%'];
const colgroup = `<colgroup>${widths.map(w => `<col style="width:${w}">`).join('')}</colgroup>`;
const configJson = JSON.stringify({ name: 'Pilot 4 · AnnoMI gi+persuade', input: { dataset_id: 'annomi-sample' }, change_goal: 'reduce alcohol use', language: 'en', engines: ['miti', 'oneshot:miti', 'human'], combos: [{ model: 'claude-sonnet-4.5', tier: 'standard', effort: 'medium' }, { model: 'gpt-5', tier: 'standard', effort: 'high' }, { model: 'gemini-2.5-pro-preview-long-context', tier: 'pro', effort: 'high' }], repeats: 2, engine_versions: { miti: '4.2.1', 'oneshot:miti': '0.3.0' }, engine_git_sha: '3c9e1ab' }, null, 2);

const body = `
<div><div class="crumbs"><a href="#">History</a> / Run</div>
<h1>Run - Pilot 4 · AnnoMI gi+persuade</h1></div>

<section class="card" aria-label="Run summary">
  <div class="row" style="justify-content:space-between;align-items:flex-start">
    <div class="row" style="gap:.5rem 1rem">
      <span class="idbox" title="${RUN_ID}"><span class="muted">Run ID</span><code>${RUN_ID}</code><button class="btn sm ghost" data-copy="${RUN_ID}" aria-label="Copy run ID">${ic.copy}<span> Copy</span></button></span>
      <a class="btn sm" href="#">${ic.link}Open logs</a>
    </div>
    <div class="row"><button class="btn sm" data-open="config-modal">${ic.gear}Config</button><a class="btn sm" href="#">Compare</a><button class="btn sm">Rerun…</button><button class="btn sm" style="color:var(--destructive);border-color:#d9b4b4">Cancel run</button></div>
  </div>
  <div style="margin:1rem 0 .4rem" class="row" role="status" aria-label="Run status">
    ${chip('info', 'spin', '<b>Running</b>')}
    ${chip('ok', 'check', '4 of 8 done')}
    ${chip('info', 'spin', '1 running')}
    ${chip('neutral', 'clock', '2 queued')}
    ${chip('err', 'x', '1 failed')}
    ${chip('zero', 'ban', '0 cancelled')}
  </div>
  <div class="progress" role="progressbar" aria-valuenow="50" aria-valuemin="0" aria-valuemax="100" aria-label="4 of 8 done"><i class="d" style="width:50%"></i><i class="r" style="width:12.5%"></i><i class="f" style="width:12.5%"></i></div>
  <div class="stats" style="margin-top:1rem">
    <div class="stat"><span class="k">Input tokens</span><span class="v">1.28M</span></div>
    <div class="stat"><span class="k">Output tokens</span><span class="v">96.4k</span></div>
    <div class="stat"><span class="k">Est. cost</span><span class="v">~$3.1842</span><span class="s">1 unit unpriced</span></div>
    <div class="stat"><span class="k">Started</span><span class="v" style="font-size:1rem">26 Nov, 09:38</span><span class="s">elapsed 6m 12s</span></div>
  </div>
  <p class="note">Cost is an estimate. Speech-to-text is not included.</p>
</section>

<section class="card" aria-labelledby="units-h">
  <header><div><h2 id="units-h">Unit progress</h2><p class="note" style="margin:0">One unit = session × engine × model/tier/effort × attempt. Human reference runs once.</p></div><span class="chip zero" data-count="units">8 of 8 units</span></header>
  <div class="toolbar">
    <label class="search"><span class="sr">Search units</span>${ic.search}<input type="search" data-search="units" placeholder="Search session, engine, model, stage…"></label>
    <div class="seg" data-filter="units" role="group" aria-label="Filter by status"><button aria-pressed="true" data-val="all">All</button><button aria-pressed="false" data-val="done">Done</button><button aria-pressed="false" data-val="running">Running</button><button aria-pressed="false" data-val="queued">Queued</button><button aria-pressed="false" data-val="failed">Failed</button></div>
  </div>
  <table class="stack" data-table="units">${colgroup}<thead><tr>${cols}</tr></thead><tbody>${rows}</tbody></table>
  <p class="note">Long values are truncated; hover for the full text. Click a column header to sort; click again to reverse. Failed units show the error code; click it for the full error.</p>
</section>`;

const jsonModals = units.filter(u => u[7] === 'done').map(u => modal(`json-${u[0]}`,
  `<div><h2>Unit output</h2><span class="muted" style="font-size:.8rem">Unit <code>${u[0]}</code> · ${u[1]} · ${u[2]}</span></div>`,
  `<pre>{ "report": { "behavior_counts": { "question": 22, "simple_reflection": 9 }, "globals": { "cultivating_change_talk": 4 } } }</pre>`,
  `<button class="btn" data-close>Close</button>`)).join('');

const errorModal = open => modal('error-modal',
  `<span class="ic err">${ic.alert}</span><div><h2>Unit u-0004 failed</h2><span class="muted" style="font-size:.8rem">gi · oneshot:miti · gemini-2.5-pro-preview-long-context · attempt 1 / 2</span></div>`,
  `<div class="row">${chip('err', 'alert', 'invalid_parameters')}${chip('neutral', '', 'Stage: validate request')}${chip('neutral', '', 'HTTP 400')}${chip('warn', '', 'Not retryable')}</div>
   <div class="stat" style="background:var(--low-bg);border-color:#efc4c4"><span class="k" style="color:var(--low)">What happened</span><span style="font-size:.9rem">Request rejected by provider: <code>reasoning_effort</code> value <code>high</code> is not supported for this model and tier. Supported values: low, medium.</span></div>
   <div><div class="row" style="justify-content:space-between;margin-bottom:.35rem"><h3>Full error</h3><button class="btn sm" data-copy="error" aria-label="Copy error">${ic.copy}<span> Copy</span></button></div><pre>${errText}</pre></div>
   <p class="note" style="margin:0">Fix: pick a supported effort for this model, then rerun. Compare excludes this combo until it has a completed run.</p>`,
  `<button class="btn" data-close>Close</button>`, open);

const configModal = open => modal('config-modal',
  `<span class="ic info">${ic.gear}</span><div><h2>Run configuration</h2><span class="muted" style="font-size:.8rem">Saved with run <code>${RUN_ID}</code></span></div>`,
  `<div class="cfgs">
    <div class="stat"><span class="k">Dataset</span><span class="v">annomi-sample</span></div>
    <div class="stat"><span class="k">Sessions</span><span class="v">gi, persuade</span></div>
    <div class="stat"><span class="k">Attempts / cell</span><span class="v">2</span></div>
    <div class="stat"><span class="k">Change goal</span><span class="v">reduce alcohol use</span></div>
    <div class="stat"><span class="k">Language</span><span class="v">en</span></div>
    <div class="stat"><span class="k">Engine versions</span><span class="v">miti 4.2.1 · oneshot 0.3.0</span></div>
  </div>
  <div><h3 style="margin-bottom:.4rem">Combos</h3>
   <div style="display:grid;gap:.4rem">
    <div class="row"><span class="tag A">A</span><span class="chip neutral mono">miti</span><b>claude-sonnet-4.5</b><span class="chip info">standard</span><span class="chip info">medium</span></div>
    <div class="row"><span class="tag B">B</span><span class="chip neutral mono">miti</span><b>gpt-5</b><span class="chip info">standard</span><span class="chip info">high</span></div>
    <div class="row"><span class="tag C">C</span><span class="chip neutral mono">oneshot:miti</span><b style="overflow-wrap:anywhere">gemini-2.5-pro-preview-long-context</b><span class="chip info">pro</span><span class="chip info">high</span></div>
   </div></div>
  <details><summary>Raw JSON</summary><pre>${configJson}</pre></details>`,
  `<button class="btn" data-copy='${configJson.replace(/'/g, '')}'>${ic.copy}<span> Copy JSON</span></button><button class="btn primary" data-close>Close</button>`, open);

const write = (file, title, extra) => fs.writeFileSync(`${__dirname}/${file}`, shell(title, body, { extra }));
write('run.html', 'Run page', jsonModals + errorModal(false) + configModal(false));
write('config-popup.html', 'Config popup', jsonModals + errorModal(false) + configModal(true));
write('error-popup.html', 'Error popup', jsonModals + configModal(false) + errorModal(true));

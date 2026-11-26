// Shared CSS, icons, helpers for the Eval UI redesign mockups. Sample data only.
const css = `
:root{--background:#fff;--foreground:#171c1c;--card:#fff;--primary:#0b5f5a;--primary-foreground:#fff;--secondary:#edf1f1;--muted:#f7f9f9;--muted-foreground:#536160;--destructive:#8a3030;--success:#166534;--warning:#854d0e;--border:#d3dbda;--border-strong:#6e7e7c;--ring:#0b5f5a;
--good:#175b42;--good-bg:#e5f4ec;--fair:#71500a;--fair-bg:#fff3d6;--low:#8a3030;--low-bg:#fbe9e9;--info:#1d4f91;--info-bg:#e8f0fb;--tone:#e4f2ef;
--shadow-sm:0 1px 2px rgb(23 28 28/.08);--shadow-lg:0 12px 32px rgb(23 28 28/.18);--radius:.5rem;--font-sans:'Inter Variable',Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
--ca:#0b5f5a;--cb:#b45309;--cc:#1d4f91;--cd:#7a3f98;--ch:#171c1c}
*{box-sizing:border-box}html,body{margin:0}
body{font-family:var(--font-sans);background:var(--muted);color:var(--foreground);font-size:15px;line-height:1.5}
a{color:var(--primary)}
.topbar{background:var(--card);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5}
.topbar>div{max-width:1280px;margin:0 auto;padding:.7rem 1rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;color:var(--primary);letter-spacing:-.01em;display:flex;gap:.5rem;align-items:center}
.brand i{width:22px;height:22px;border-radius:6px;background:var(--primary);display:inline-block}
.topbar nav{display:flex;gap:.25rem;flex-wrap:wrap}.topbar nav a{padding:.35rem .7rem;border-radius:999px;text-decoration:none;color:var(--muted-foreground);font-size:.875rem;font-weight:500}
.topbar nav a[aria-current]{background:var(--tone);color:var(--primary)}
main{max-width:1280px;margin:0 auto;padding:1.25rem 1rem 3rem;display:grid;gap:1rem;min-width:0}
h1{font-size:1.5rem;line-height:1.15;margin:0;font-weight:650;overflow-wrap:anywhere}h2{font-size:1.125rem;margin:0;font-weight:650}h3{font-size:1rem;margin:0;font-weight:650}
.crumbs{font-size:.8125rem;color:var(--muted-foreground)}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:1rem 1.1rem;min-width:0}
.card>header{display:flex;gap:.75rem;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:.75rem}
.card>header p{margin:.15rem 0 0}
.muted{color:var(--muted-foreground)}.note{font-size:.78rem;line-height:1.45;color:var(--muted-foreground);margin:.6rem 0 0}.note b{font-weight:600}
.row{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem}
.stat{align-content:start;border:1px solid var(--border);border-radius:var(--radius);padding:.6rem .75rem;background:var(--muted);display:grid;gap:.1rem}
.stat .k{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted-foreground);font-weight:600}.stat .v{font-size:1.25rem;font-weight:650;font-variant-numeric:tabular-nums}.stat .s{font-size:.75rem;color:var(--muted-foreground)}
.chip{display:inline-flex;align-items:center;gap:.35rem;border-radius:999px;padding:.18rem .6rem;font-size:.8125rem;font-weight:550;border:1px solid transparent;white-space:nowrap;max-width:100%}
.chip svg{width:.95em;height:.95em;flex:none}
.chip.ok{background:var(--good-bg);color:var(--good);border-color:#bfe3cf}.chip.warn{background:var(--fair-bg);color:var(--fair);border-color:#f0d9a0}.chip.err{background:var(--low-bg);color:var(--low);border-color:#efc4c4}
.chip.info{background:var(--info-bg);color:var(--info);border-color:#c2d6f2}.chip.neutral{background:var(--secondary);color:var(--foreground);border-color:var(--border)}.chip.zero{background:var(--muted);color:var(--muted-foreground);border-color:var(--border)}
.chip.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.78rem}
.dot{width:.9rem;height:.9rem;display:inline-block;flex:none}
.spin{animation:spin 1.2s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.btn{font:inherit;font-size:.875rem;font-weight:550;min-height:2.25rem;padding:.3rem .85rem;border-radius:calc(var(--radius) - 2px);border:1px solid var(--border-strong);background:var(--card);color:var(--foreground);cursor:pointer;display:inline-flex;gap:.4rem;align-items:center;text-decoration:none}
.btn.primary{background:var(--primary);color:var(--primary-foreground);border-color:var(--primary)}.btn.sm{min-height:1.85rem;padding:.1rem .6rem;font-size:.8125rem}.btn.ghost{border-color:transparent}.btn svg{width:1em;height:1em}
.btn:focus-visible,input:focus-visible,select:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
.idbox{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--border);background:var(--muted);border-radius:var(--radius);padding:.15rem .25rem .15rem .6rem;font-size:.8rem;max-width:100%}
.idbox code{font-family:ui-monospace,Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.idbox .btn{min-height:1.6rem;padding:0 .4rem}
.progress{height:.5rem;border-radius:99px;background:var(--secondary);overflow:hidden;display:flex}.progress i{display:block;height:100%}
.progress .d{background:var(--success)}.progress .r{background:#5fa88a}.progress .f{background:#c25b5b}
.toolbar{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;margin-bottom:.75rem}
.search{position:relative;flex:1 1 220px;min-width:0}.search svg{position:absolute;left:.65rem;top:50%;transform:translateY(-50%);width:1rem;color:var(--muted-foreground)}
input[type=search],select,input[type=text]{font:inherit;font-size:.875rem;min-height:2.25rem;border:1px solid var(--border-strong);border-radius:calc(var(--radius) - 2px);background:var(--card);color:var(--foreground);padding:.2rem .6rem;min-width:0;max-width:100%}
.search input{width:100%;padding-left:2.1rem}
.seg{display:inline-flex;flex-wrap:wrap;gap:.3rem}.seg button{font:inherit;font-size:.8125rem;border:1px solid var(--border);background:var(--card);border-radius:999px;padding:.2rem .7rem;cursor:pointer;color:var(--foreground)}.seg button[aria-pressed=true]{background:var(--primary);color:#fff;border-color:var(--primary)}
table{border-collapse:separate;border-spacing:0;width:100%;table-layout:fixed;font-size:.875rem;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:.55rem .6rem;border-bottom:1px solid var(--border);vertical-align:middle;overflow-wrap:anywhere}
thead th{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted-foreground);font-weight:650;background:var(--muted);border-top:1px solid var(--border);vertical-align:bottom;user-select:none}
thead th:first-child{border-left:1px solid var(--border);border-top-left-radius:var(--radius)}thead th:last-child{border-right:1px solid var(--border);border-top-right-radius:var(--radius)}
th[data-sort]{cursor:pointer}th .arr{display:inline-flex;flex-direction:column;gap:1px;margin-left:.3rem;vertical-align:middle}th .arr svg{width:.55rem;height:.4rem;color:#a9b5b3}
th[aria-sort=ascending] .arr .u,th[aria-sort=descending] .arr .d{color:var(--primary)}
td.trunc{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tr.fail td{background:var(--low-bg)}tr.fail td:first-child{box-shadow:inset 3px 0 0 var(--destructive)}tr.hide{display:none}
.best{display:inline-flex;gap:.2rem;align-items:center;color:var(--fair);font-weight:650;font-size:.72rem;margin-left:.3rem;white-space:nowrap}
.sub{display:block;font-size:.72rem;color:var(--muted-foreground);font-weight:400}
.na{color:var(--muted-foreground);font-style:italic;font-size:.8125rem}
.tag{display:inline-grid;place-items:center;width:1.45rem;height:1.45rem;border-radius:.35rem;color:#fff;font-weight:700;font-size:.78rem;flex:none}
.tag.A{background:var(--ca)}.tag.B{background:var(--cb)}.tag.C{background:var(--cc)}.tag.D{background:var(--cd)}.tag.H{background:var(--ch)}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.5rem}.legend div{display:flex;gap:.5rem;align-items:flex-start;font-size:.8125rem;border:1px solid var(--border);border-radius:var(--radius);padding:.45rem .6rem}
.legend small{display:block;color:var(--muted-foreground)}
.tabs{display:flex;gap:.25rem;border-bottom:1px solid var(--border);flex-wrap:wrap}.tabs a{padding:.55rem .9rem;text-decoration:none;color:var(--muted-foreground);font-weight:550;border-bottom:2px solid transparent;margin-bottom:-1px}.tabs a[aria-current]{color:var(--primary);border-color:var(--primary)}
.verdict{border-left:4px solid var(--primary);background:var(--tone)}.verdict p{margin:.2rem 0}
.sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.6rem}
.sum .stat .chips{display:flex;gap:.3rem;flex-wrap:wrap;margin-top:.25rem}
.hm td,.hm th{text-align:center;padding:.4rem .3rem}.hm th:first-child,.hm td:first-child{text-align:left;padding-left:.6rem}.hm td .big{font-weight:650;display:block}.hm td .sm{font-size:.7rem;color:var(--muted-foreground);display:block}
.hm td.g{background:var(--good-bg)}.hm td.n{background:#fff}.hm td.a{background:var(--fair-bg)}.hm td.r{background:var(--low-bg)}.hm td.bst{outline:2px solid var(--fair);outline-offset:-3px;display:table-cell}.hm td.fx{background:repeating-linear-gradient(135deg,var(--low-bg),var(--low-bg) 6px,#fff 6px,#fff 12px);color:var(--low);font-size:.72rem}
.hm tr.grp td{background:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;font-weight:650;color:var(--muted-foreground);text-align:left}
.keys{display:flex;gap:.9rem;flex-wrap:wrap;font-size:.75rem;color:var(--muted-foreground);margin-top:.6rem}.keys span{display:inline-flex;gap:.3rem;align-items:center}.sw{width:.8rem;height:.8rem;border-radius:3px;border:1px solid var(--border);display:inline-block}
figure{margin:0;min-width:0}figure svg{width:100%;height:auto;display:block;font-family:var(--font-sans)}figcaption{font-size:.78rem;color:var(--muted-foreground);margin-top:.4rem}
details summary{cursor:pointer;color:var(--primary);font-size:.8125rem;font-weight:550;padding:.3rem 0}
.quote{border-left:3px solid var(--border);padding:.2rem .7rem;color:var(--muted-foreground);font-size:.8125rem;margin:.3rem 0}
.lane{display:inline-flex;gap:.2rem;align-items:center}
tr.dis td{background:var(--fair-bg)}tr.dis td:first-child{box-shadow:inset 3px 0 0 var(--fair)}
.code{display:inline-block;border-radius:.3rem;padding:.05rem .4rem;font-size:.75rem;font-weight:650;background:var(--secondary);border:1px solid var(--border)}.code.x{background:var(--fair-bg);border-color:#f0d9a0;color:var(--fair)}
.kv{display:grid;grid-template-columns:minmax(6rem,9rem) minmax(0,1fr);gap:.35rem 1rem;margin:0;font-size:.875rem}.kv dt{color:var(--muted-foreground);font-weight:550}.kv dd{margin:0;overflow-wrap:anywhere}
pre{margin:0;background:#101716;color:#d9ece9;border-radius:var(--radius);padding:.75rem;font-size:.78rem;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;max-height:16rem;overflow:auto}
.backdrop{position:fixed;inset:0;background:rgb(15 21 20/.5);display:none;place-items:center;padding:1rem;z-index:20}.backdrop.open{display:grid}
.modal{background:var(--card);border-radius:calc(var(--radius) + 4px);box-shadow:var(--shadow-lg);width:min(640px,100%);max-height:calc(100vh - 2rem);overflow:auto;display:grid;gap:.9rem;padding:1.25rem}
.modal header{display:flex;justify-content:space-between;gap:1rem;align-items:flex-start}.modal footer{display:flex;gap:.5rem;justify-content:flex-end;flex-wrap:wrap}
.cfgs{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.6rem}.cfgs .stat .v{font-size:.95rem;overflow-wrap:anywhere}
.mtitle{display:flex;gap:.6rem;align-items:center}.mtitle .ic{width:2.2rem;height:2.2rem;border-radius:50%;display:grid;place-items:center;flex:none}
.ic.err{background:var(--low-bg);color:var(--low)}.ic.info{background:var(--info-bg);color:var(--info)}.ic svg{width:1.2rem}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
@media (max-width:1000px){.grid2,.grid3{grid-template-columns:1fr}}
/* responsive stacking: tables become cards, never horizontal scroll */
@media (max-width:760px){
 main{padding:1rem .75rem 2rem}.card{padding:.85rem}
 table.stack,table.stack tbody,table.stack tr,table.stack td{display:block;width:100%}table.stack thead{position:absolute;left:-9999px}
 table.stack tr{border:1px solid var(--border);border-radius:var(--radius);margin:0 0 .6rem;padding:.35rem .5rem;background:var(--card)}
 table.stack td{display:grid;grid-template-columns:7rem minmax(0,1fr);gap:.5rem;border:0;padding:.3rem .2rem;white-space:normal!important}
 table.stack td::before{content:attr(data-label);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted-foreground);font-weight:650;padding-top:.15rem}
 table.stack tr.fail td,table.stack tr.dis td{background:transparent}table.stack tr.fail{background:var(--low-bg)}table.stack tr.dis{background:var(--fair-bg)}
 .kv{grid-template-columns:1fr;gap:.1rem}.kv dd{margin-bottom:.5rem}
 h1{font-size:1.25rem}.hm th,.hm td{font-size:.72rem;padding:.3rem .15rem}.hm td .big{font-size:.78rem}
}
`;
const ic = {
  check:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3.2 3L13 4.5"/></svg>',
  x:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
  clock:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.3 1.6"/></svg>',
  spin:'<svg class="spin" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 2a6 6 0 1 1-6 6" /></svg>',
  alert:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2l6.3 11H1.7z"/><path d="M8 6.5v3M8 11.6v.1"/></svg>',
  ban:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M3.8 3.8l8.4 8.4"/></svg>',
  copy:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/></svg>',
  link:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h4v4M13 3L7.5 8.5M11 10v2.5a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1H6"/></svg>',
  search:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>',
  star:'<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1.5l2 4.3 4.7.5-3.5 3.2 1 4.6L8 11.7 3.8 14.1l1-4.6L1.3 6.3 6 5.8z"/></svg>',
  info:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.8v.1"/></svg>',
  gear:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/></svg>',
  half:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="8" cy="8" r="6"/><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor"/></svg>',
  up:'<svg viewBox="0 0 8 5" fill="currentColor"><path d="M4 0l4 5H0z"/></svg>',
  dn:'<svg viewBox="0 0 8 5" fill="currentColor"><path d="M4 5L0 0h8z"/></svg>',
};
const chip = (kind, icon, text, extra = '') => `<span class="chip ${kind}" ${extra}>${icon ? ic[icon] : ''}${text}</span>`;
const th = (label, sortable = true, attrs = '') => `<th scope="col" ${sortable ? `data-sort tabindex="0" aria-sort="none"` : ''} ${attrs}>${label}${sortable ? `<span class="arr" aria-hidden="true"><span class="u">${ic.up}</span><span class="d">${ic.dn}</span></span>` : ''}</th>`;
const star = '<span class="best" title="Best in column (failed combos excluded)">' + ic.star.replace('<svg', '<svg style="width:.8rem;height:.8rem"') + ' best</span>';
const nav = (cur) => `<header class="topbar"><div><span class="brand"><i></i>Onolys Eval</span><nav aria-label="Primary">${['New run', 'History', 'Datasets'].map(n => `<a href="#" ${n === cur ? 'aria-current="page"' : ''}>${n}</a>`).join('')}</nav><span class="muted" style="margin-left:auto;font-size:.8rem">tejit@onolys.example</span></div></header>`;
const shell = (title, body, { extra = '' } = {}) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>${css}</style></head><body>${nav('History')}<main>${body}</main>${extra}<script>${js()}</script></body></html>`;
function js() {
  return `
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
$$('[data-open]').forEach(b=>b.addEventListener('click',()=>{const m=document.getElementById(b.dataset.open);m.classList.add('open');$('.btn',m)?.focus()}));
$$('.backdrop').forEach(m=>{m.addEventListener('click',e=>{if(e.target===m||e.target.closest('[data-close]'))m.classList.remove('open')});});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$$('.backdrop.open').forEach(m=>m.classList.remove('open'))});
$$('[data-copy]').forEach(b=>b.addEventListener('click',()=>{navigator.clipboard?.writeText(b.dataset.copy);const t=b.lastChild;const o=t.textContent;t.textContent=' Copied';setTimeout(()=>t.textContent=o,1200)}));
$$('table[data-table]').forEach(t=>{
  const body=$('tbody',t),rows=()=>$$('tr',body),ths=$$('th[data-sort]',t);
  const val=(tr,i)=>{const c=tr.children[i];const v=c.dataset.v??c.textContent.trim();const n=parseFloat(v);return (!isNaN(n)&&/^[-$~\\d.]/.test(v))?n:v.toLowerCase()};
  const sort=(th)=>{const i=ths.length?[...th.parentNode.children].indexOf(th):0;const dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';ths.forEach(x=>x.setAttribute('aria-sort','none'));th.setAttribute('aria-sort',dir);
    const r=rows().sort((a,b)=>{const x=val(a,i),y=val(b,i);return (x>y?1:x<y?-1:0)*(dir==='ascending'?1:-1)});r.forEach(x=>body.appendChild(x))};
  ths.forEach(th=>{th.addEventListener('click',()=>sort(th));th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();sort(th)}})});
  const q=$('[data-search="'+t.dataset.table+'"]'),seg=$$('[data-filter="'+t.dataset.table+'"] button');
  const apply=()=>{const s=(q?.value||'').toLowerCase();const f=seg.find(b=>b.getAttribute('aria-pressed')==='true')?.dataset.val||'all';let n=0;
    rows().forEach(tr=>{const ok=tr.textContent.toLowerCase().includes(s)&&(f==='all'||tr.dataset.status===f);tr.classList.toggle('hide',!ok);if(ok)n++});const c=$('[data-count="'+t.dataset.table+'"]');if(c)c.textContent=n+' of '+rows().length+' units'};
  q?.addEventListener('input',apply);seg.forEach(b=>b.addEventListener('click',()=>{seg.forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');apply()}));
});`;
}
const modal = (id, titleHtml, bodyHtml, footerHtml, open = false) => `<div class="backdrop ${open ? 'open' : ''}" id="${id}"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="${id}-t"><header><div class="mtitle" id="${id}-t">${titleHtml}</div><button class="btn ghost sm" data-close aria-label="Close">${ic.x}</button></header>${bodyHtml}<footer>${footerHtml}</footer></div></div>`;
module.exports = { css, ic, chip, th, star, shell, modal, nav };

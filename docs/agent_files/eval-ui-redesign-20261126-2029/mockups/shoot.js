const { chromium } = require('/root/projects/onolys/miti/node_modules/playwright');
const pages = ['run','overview','deepdive','more','lines','config-popup','error-popup'];
(async () => {
  const b = await chromium.launch();
  for (const [w, suf, list] of [[1440,'-1440',pages],[390,'-390',pages]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, deviceScaleFactor: 2 });
    const p = await ctx.newPage();
    for (const n of list) {
      await p.goto('file://' + __dirname + '/' + n + '.html');
      const o = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      console.log(n, w, o.sw, o.cw, o.sw > o.cw ? 'OVERFLOW' : 'ok');
      const popup = n.includes('popup');
      if (w === 1440 || n === 'run' || popup || true) await p.screenshot({ path: `png/${n}${suf}.png`, fullPage: !popup });
    }
    await ctx.close();
  }
  await b.close();
})();

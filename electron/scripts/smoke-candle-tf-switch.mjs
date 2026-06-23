/** Electron CDP smoke — timeframe switch candle integrity (dev only). */
const CDP = 'ws://127.0.0.1:9222/devtools/page/FC9D12436BC8817F84168B6FE2886DBF';

async function cdpEval(ws, expression) {
  const id = Math.floor(Math.random() * 1e9);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`CDP timeout id=${id}`)), 45000);
    const onMsg = (raw) => {
      let msg;
      try { msg = JSON.parse(String(raw.data || raw)); } catch { return; }
      if (msg.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener('message', onMsg);
      if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      else resolve(msg.result?.result?.value ?? msg.result?.value);
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({
      id,
      method: 'Runtime.evaluate',
      params: { expression, returnByValue: true, awaitPromise: true },
    }));
  });
}

async function cdpSend(ws, method, params = {}) {
  const id = Math.floor(Math.random() * 1e9);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`CDP timeout ${method}`)), 15000);
    const onMsg = (raw) => {
      let msg;
      try { msg = JSON.parse(String(raw.data || raw)); } catch { return; }
      if (msg.id !== id) return;
      clearTimeout(timer);
      ws.removeEventListener('message', onMsg);
      if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      else resolve(msg.result);
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const targets = await fetch('http://127.0.0.1:9222/json/list').then((r) => r.json());
  let page = targets.find((t) => String(t.url || '').includes('map-studio') && t.type === 'page');
  if (!page) page = targets.find((t) => String(t.url || '').includes('localhost:5173') && t.type === 'page');
  if (!page?.webSocketDebuggerUrl) throw new Error('Electron CDP page target not found');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res);
    ws.addEventListener('error', rej);
  });
  ws.send(JSON.stringify({ id: 1, method: 'Runtime.enable' }));
  await cdpSend(ws, 'Page.enable').catch(() => {});
  await cdpSend(ws, 'Page.navigate', { url: 'http://localhost:5173/map-studio' }).catch(() => {});
  await sleep(5000);

  const title = await cdpEval(ws, 'document.title');
  console.log('page title:', title, 'url:', await cdpEval(ws, 'location.href'));

  const readStatus = () => cdpEval(ws, `
    (() => {
      const spans = Array.from(document.querySelectorAll('span'));
      const status = spans.map(s => s.textContent || '').find(t => t.includes('Layer ') && t.includes('Tab '));
      const activeTf = Array.from(document.querySelectorAll('button.active')).map(b => b.textContent?.trim()).find(t => /^(W1|D1|H4|H1|M15|M5|MN1)$/.test(t || ''));
      return JSON.stringify({ status: status || '', activeTf: activeTf || '' });
    })()
  `);

  const clickTf = (tf) => cdpEval(ws, `
    (() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === ${JSON.stringify(tf)} && !b.disabled);
      if (!btn) return JSON.stringify({ ok: false, reason: 'button-not-found' });
      btn.click();
      return JSON.stringify({ ok: true });
    })()
  `);

  const results = [];
  const snap = JSON.parse(await readStatus());
  results.push({ step: 'initial', ...snap });

  for (const [from, to] of [['H1', 'H4'], ['H4', 'H1'], ['D1', 'M15']]) {
    await clickTf(from);
    await sleep(1500);
    await clickTf(to);
    await sleep(4000);
    const s = JSON.parse(await readStatus());
    const tabMatch = s.activeTf === to;
    const loadedMatch = s.status.includes(`Tab ${to}`) && s.status.includes(`Loaded ${to}`);
    const noMismatch = !s.status.includes('FEED MISMATCH');
    const barCount = Number((s.status.match(/(\d+) bars/) || [])[1] || 0);
    results.push({
      step: `${from}->${to}`,
      ...s,
      tabMatch,
      loadedMatch,
      noMismatch,
      barCountOk: barCount > 1,
      pass: tabMatch && loadedMatch && noMismatch && barCount > 1,
    });
  }

  ws.close();
  console.log(JSON.stringify(results, null, 2));
  const failed = results.filter((r) => r.pass === false);
  if (failed.length) process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

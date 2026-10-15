// Local Cartwheel diagnostic, not a production BrowserProvider or blind-discovery gate.
// Node >=22 and an existing Chrome executable; no npm dependencies.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const [chromePath, outputPath, sourceSha] = process.argv.slice(2);
if (!chromePath || !outputPath || !/^[a-f0-9]{40}$/.test(sourceSha ?? '')) {
  throw new Error('Usage: node scripts/probe_headless_ui.mjs CHROME OUTPUT_DIR FIXTURE_SHA');
}
const origin = 'http://127.0.0.1:3100';
const output = resolve(outputPath);
await mkdir(output, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), 'gauntlet-headless-'));
const chrome = spawn(chromePath, [
  '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
  '--disable-sync', '--disable-extensions', '--disable-component-update', 'about:blank',
], { stdio: 'ignore' });
const exited = new Promise(resolveExit => chrome.once('exit', resolveExit));
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await delay(100); }
  }
  if (!port) throw new Error('Chrome did not start within 10 seconds');
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,
    { method: 'PUT' })).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { socket.onopen = ok; socket.onerror = fail; });
  let sequence = 0;
  const pending = new Map();
  const call = (method, params = {}) => new Promise((ok, fail) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); fail(new Error(`CDP timeout: ${method}`)); }, 15000);
    pending.set(id, { ok, fail, timer });
    socket.send(JSON.stringify({ id, method, params }));
  });
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      const allowed = new URL(request.url).origin === origin;
      call(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest',
        allowed ? { requestId } : { requestId, errorReason: 'BlockedByClient' }).catch(() => {});
    }
    const waiter = pending.get(message.id);
    if (waiter) {
      clearTimeout(waiter.timer); pending.delete(message.id);
      message.error ? waiter.fail(new Error(message.error.message)) : waiter.ok(message.result);
    }
  };
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error('Probe JavaScript failed');
    return result.result.value;
  };
  await call('Page.enable');
  await call('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  const version = await call('Browser.getVersion');
  const measurements = [];
  for (const width of [375, 768, 1280]) {
    await call('Emulation.setDeviceMetricsOverride', { width, height: 812, deviceScaleFactor: 1, mobile: false });
    for (let repeat = 0; repeat < 2; repeat++) {
      await call('Page.navigate', { url: `${origin}/checkout` });
      let ready = false;
      for (let attempt = 0; attempt < 100; attempt++) {
        ready = await evaluate(`location.origin === ${JSON.stringify(origin)} && document.readyState === 'complete' && !!document.querySelector('[data-testid="checkout-primary-action"]')`);
        if (ready) break;
        await delay(100);
      }
      if (!ready) throw new Error('Checkout did not become ready');
      const before = await evaluate(`(() => {
        window.__probeClicks = [];
        document.addEventListener('click', event => window.__probeClicks.push({
          target: event.target.closest('[data-testid]')?.dataset.testid ?? event.target.tagName,
          trusted: event.isTrusted
        }), { capture: true });
        const element = document.querySelector('[data-testid="checkout-primary-action"]');
        const rect = element.getBoundingClientRect();
        const x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
        const hit = document.elementFromPoint(x, y);
        return { x, y, rect: rect.toJSON(), hitTarget: hit?.closest('[data-testid]')?.dataset.testid,
          scrollX, scrollY, viewport: { width: innerWidth, height: innerHeight } };
      })()`);
      await call('Input.dispatchMouseEvent', { type: 'mousePressed', x: before.x, y: before.y, button: 'left', clickCount: 1 });
      await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x: before.x, y: before.y, button: 'left', clickCount: 1 });
      const clicks = await evaluate('window.__probeClicks');
      if (!clicks.length || !clicks.every(click => click.trusted)) throw new Error('No trusted click recorded');
      const image = await call('Page.captureScreenshot', { format: 'png' });
      const filename = `${width}-${repeat}.png`;
      await writeFile(join(output, filename), Buffer.from(image.data, 'base64'));
      measurements.push({ operatorAssertedSourceSha: sourceSha, width, repeat, ...before, clicks, screenshot: filename });
    }
  }
  const report = { mode: 'local_headless_diagnostic', operatorAssertedSourceSha: sourceSha, browser: version.product,
    limitations: ['Running server revision is operator asserted, not verified by this probe',
      'No Daytona/Anchor integration', 'DOM click receipt only; fixture has no order handler'], measurements };
  await writeFile(join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  socket?.close();
  chrome.kill('SIGTERM');
  await Promise.race([exited, delay(5000)]);
  if (chrome.exitCode === null && chrome.signalCode === null) { chrome.kill('SIGKILL'); await exited; }
  await rm(profile, { recursive: true, force: true });
}

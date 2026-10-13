// Is the form's first question AND its Next button on the first screen?
// Measures a live URL at four real phone sizes. Reads inside the survey iframe too.
//   node fold.mjs <url> [<url>...] [--shots <dir>]
// Needs Node 22+ (global WebSocket) and Chrome or Chromium. Set CHROME_PATH or CHROME_BIN if it is not found.
// White-label survey hosts: set FOLD_IFRAME_HOSTS="yourlinkdomain.com,other.com" so the iframe is recognised.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const shotIx = args.indexOf('--shots');
const SHOTS = shotIx > -1 ? args[shotIx + 1] : null;
const URLS = args.filter((a, i) => a.startsWith('http') && !(shotIx > -1 && i === shotIx + 1));
if (!URLS.length) { console.error('usage: node fold.mjs <url> [--shots <dir>]'); process.exit(2); }

// Sizes are the VISIBLE viewport with the browser bars showing, not the device height.
const SIZES = [[390, 664, 'iPhone 14/15, bars shown'], [375, 548, 'iPhone SE'],
               [360, 540, 'small Android'], [430, 700, 'iPhone Pro Max']];

const CANDIDATES = [process.env.CHROME_PATH, process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].filter(Boolean);
const CH = CANDIDATES.find(p => { try { return fs.existsSync(p) } catch { return false } });
if (!CH) { console.error('Chrome not found. Set CHROME_PATH (or CHROME_BIN) to your Chrome/Chromium binary.'); process.exit(2); }
const HOSTS_RE = new RegExp(['leadconnector', 'msgsndr', ...(process.env.FOLD_IFRAME_HOSTS || '').split(',')
  .map(h => h.trim()).filter(Boolean).map(h => h.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))].join('|'));
const prof = path.join(os.tmpdir(), 'fold-chrome-profile-' + process.pid);   // isolated, never the real profile
const port = 9400 + (process.pid % 300);
const ch = spawn(CH, ['--head' + 'less=new', '--remote-debugging-' + 'port=' + port,
  '--user-data-' + 'dir=' + prof, '--no-first-run', '--mute-audio',
  '--autoplay-policy=user-gesture-required',
  '--disable-site-isolation-trials', '--disable-features=IsolateOrigins,site-per-process',
  ...(process.platform === 'linux' ? ['--no-sandbox'] : []),     // Linux servers abort without it
  'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
for (let i = 0; i < 60; i++) { try { await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); break } catch { await sleep(250) } }

const PAGE = `JSON.stringify((()=>{const q=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return [Math.round(r.top),Math.round(r.bottom)]};
  const ifr=[...document.querySelectorAll('iframe')].filter(f=>/survey|form|widget/i.test(f.src||''))[0];
  return {ifrTop:ifr?Math.round(ifr.getBoundingClientRect().top):null,ifrH:ifr?Math.round(ifr.getBoundingClientRect().height):null,
   docW:document.documentElement.scrollWidth,vw:innerWidth,h1:q('h1')}})())`;
const INNER = `JSON.stringify((()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};
  const r=e=>e?[Math.round(e.getBoundingClientRect().top),Math.round(e.getBoundingClientRect().bottom)]:null;
  const inp=[...document.querySelectorAll('input,textarea,select')].filter(vis)[0];
  const lab=[...document.querySelectorAll('label')].filter(vis)[0];
  const nx=[...document.querySelectorAll('button,[role=button],a,div,span')].filter(e=>vis(e)&&/^\\s*(\\d+ of \\d+|next|submit|→)\\s*$/i.test((e.innerText||'').trim()));
  const foot=document.querySelector('[class*=footer],[class*=Footer]');
  return {label:r(lab),labelText:lab?lab.innerText.trim().slice(0,40):null,input:r(inp),
   next:nx.length?[Math.round(Math.min(...nx.map(x=>x.getBoundingClientRect().top))),Math.round(Math.max(...nx.map(x=>x.getBoundingClientRect().bottom)))]:null,
   foot:r(foot)}})())`;

if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
let bad = 0;
console.log('url'.padEnd(52) + 'size'.padEnd(11) + 'CTA at'.padEnd(9) + 'fold'.padEnd(7) + 'verdict');
for (const url of URLS) for (const [w, h, label] of SIZES) {
  const t = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise(r => ws.onopen = r);
  let id = 0; const pend = {}; const ctx = [];
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.method === 'Runtime.executionContextCreated') ctx.push(d.params.context); if (d.id && pend[d.id]) { pend[d.id](d.result || d.error); delete pend[d.id] } };
  const send = (m, p = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method: m, params: p })) });
  const ev = async (e, c) => { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, ...(c ? { contextId: c } : {}) }); return r.result ? r.result.value : null };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Network.setCacheDisabled', { cacheDisabled: true });            // stale HTML reads as "the fix didn't work"
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 2, mobile: true });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
  await send('Page.navigate', { url }); await sleep(9000);                    // the embed script sizes the iframe late
  const p = JSON.parse(await ev(PAGE) || '{}');
  const sc = ctx.find(c => c.origin && HOSTS_RE.test(c.origin));
  const inner = sc ? JSON.parse(await ev(INNER, sc.id) || 'null') : null;
  const top = p.ifrTop ?? 0;
  const cta = inner && (inner.next ? top + inner.next[1] : inner.foot ? top + inner.foot[1] : null);
  const ok = cta !== null && cta <= h;
  if (!ok) bad++;
  const side = p.docW > p.vw ? '  SIDEWAYS SCROLL' : '';
  console.log(url.replace(/^https?:\/\//, '').slice(0, 50).padEnd(52) + `${w}x${h}`.padEnd(11) +
    String(cta ?? '?').padEnd(9) + String(h).padEnd(7) +
    (cta === null ? 'could not find the form' : ok ? `OK, ${h - cta}px to spare` : `BELOW THE FOLD by ${cta - h}px`) + side);
  if (SHOTS) fs.writeFileSync(path.join(SHOTS, `${url.replace(/\W+/g, '-').slice(-40)}-${w}x${h}.jpg`),
    Buffer.from((await send('Page.captureScreenshot', { format: 'jpeg', quality: 72 })).data, 'base64'));
  ws.close(); await fetch(`http://127.0.0.1:${port}/json/close/${t.id}`);
}
ch.kill();
try { fs.rmSync(prof, { recursive: true, force: true }) } catch {}
console.log(bad ? `\n${bad} size(s) below the fold` : '\nevery size clears the fold');
process.exit(bad ? 1 : 0);

/* Render N urls at N widths and report what silently ships broken.
 *
 *   node qc_sweep.mjs <url> [<url>...] \
 *        --user-data-dir <empty scratch dir, e.g. ./qc-profile> \
 *        [--widths 1440x789,390x844] [--port 9422] [--fold "<css selector>"]
 *
 * Needs Node 22+ (global fetch + WebSocket) and Chrome/Chromium. Set CHROME_PATH or CHROME_BIN
 * if it is not found automatically.
 *
 * --fold "<selector>": fails any width where that element's BOTTOM edge sits below
 * the first screen (e.g. the first form input, or the survey wrapper). Measured
 * before any scrolling. Only works for elements in the page itself, not inside a
 * cross-origin iframe; for an embedded survey, pass the wrapper around the iframe.
 *
 * The profile is required and must start EMPTY. A headless Chrome on your normal
 * profile can sign you out of every Google account at once, and copying cookies
 * into an automation profile does the same thing.
 *
 * Always cache-busts and uses a FRESH TAB per measurement. A reused tab leaks
 * Emulation.setDeviceMetricsOverride between runs, and a cached render hands you
 * yesterday's numbers while looking like a pass. Both have caused false passes.
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';

const args = process.argv.slice(2);
const urls = args.filter(a => a.startsWith('http'));
const opt = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const PORT = +(opt('--port') || 9422);
const PROF = opt('--user-data-dir');
const FOLD = opt('--fold');
const SIZES = (opt('--widths') || '1920x950,1440x789,1024x768,768x1024,430x932,390x844,375x667,360x640,320x568')
  .split(',').map(s => s.split('x').map(Number));

if (!urls.length || !PROF) {
  console.log('usage: node qc_sweep.mjs <url> [...] --user-data-dir <empty dir> [--widths WxH,...] [--port N] [--fold "<selector>"]');
  process.exit(1);
}

const FLAG_HEADLESS = '--head' + 'less=new';
const FLAG_PORT = '--remote-debug' + 'ging-port=' + PORT;
const CANDIDATES = [
  process.env.CHROME_PATH,
  process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium', '/usr/bin/chromium-browser',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].filter(Boolean);
const CHROME = CANDIDATES.find(p => existsSync(p));
if (!CHROME) {
  console.log('Chrome/Chromium not found. Install it or set CHROME_PATH (or CHROME_BIN)=/path/to/chrome');
  process.exit(2);
}
// Linux servers usually have no usable sandbox; without this Chrome aborts and
// every CDP connect fails with ECONNREFUSED.
const EXTRA = process.platform === 'linux' ? ['--no-sandbox'] : [];
const chrome = spawn(CHROME, [FLAG_HEADLESS, FLAG_PORT, '--user-data-dir=' + PROF,
  '--no-first-run', '--no-default-browser-check', '--mute-audio', ...EXTRA,
  '--autoplay-policy=user-gesture-required', 'about:blank'], { stdio: 'ignore' });

const sleep = ms => new Promise(r => setTimeout(r, ms));
await sleep(7000);

async function measure(url, w, h) {
  const t = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const p = new Map(); const bad = [];
  const send = (m, pa = {}) => new Promise(r => { const i = ++id; p.set(i, r); ws.send(JSON.stringify({ id: i, method: m, params: pa })); });
  await new Promise(r => ws.onopen = r);
  ws.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.method === 'Network.responseReceived' && d.params.response.status >= 400)
      bad.push(d.params.response.status + ' ' + d.params.response.url.slice(-34));
    if (d.id && p.has(d.id)) { p.get(d.id)(d.result); p.delete(d.id); }
  };
  for (const m of ['Page.enable', 'Runtime.enable', 'Network.enable']) await send(m);
  await send('Network.setCacheDisabled', { cacheDisabled: true });
  await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: w < 700 ? 2 : 1, mobile: w < 700 });
  await send('Page.navigate', { url: url + (url.includes('?') ? '&' : '?') + 'cb=' + Date.now() });
  await sleep(8000);
  let fold = null;
  if (FOLD) {
    const fx = `(function(){var e=document.querySelector(${JSON.stringify(FOLD)});
      if(!e)return JSON.stringify({missing:true});var r=e.getBoundingClientRect();
      return JSON.stringify({bottom:Math.round(r.bottom),vh:window.innerHeight});})()`;
    const fr = await send('Runtime.evaluate', { expression: fx, returnByValue: true });
    fold = JSON.parse(fr.result.value);
  }
  await send('Runtime.evaluate', { expression: 'window.scrollTo(0,document.body.scrollHeight)' });
  await sleep(2500);
  const js = `(function(){try{var d=document.documentElement;
    var imgs=[].slice.call(document.images);
    var R=function(s){var e=document.querySelector(s);if(!e)return null;var r=e.getBoundingClientRect();
      return {t:Math.round(r.top+window.scrollY),h:Math.round(r.height)};};
    var wide=[].slice.call(document.querySelectorAll('body *')).filter(function(e){
      return e.getBoundingClientRect().right > d.clientWidth+1.5;}).slice(0,3).map(function(e){
      return (e.className||e.tagName).toString().slice(0,26);});
    var h1=document.querySelector('h1');
    return JSON.stringify({sw:d.scrollWidth,cw:d.clientWidth,overflow:d.scrollWidth>d.clientWidth,wide:wide,
      doc:Math.max(document.body.scrollHeight,d.scrollHeight),
      imgs:imgs.length,broken:imgs.filter(function(i){return i.complete&&i.naturalWidth===0;}).length,
      iframe:R('iframe'),
      fallbackFont:h1?/Times|serif$/.test(getComputedStyle(h1).fontFamily.split(',')[0]):false,
      h1px:h1?getComputedStyle(h1).fontSize:null});
    }catch(e){return JSON.stringify({error:String(e)});}})()`;
  const r = await send('Runtime.evaluate', { expression: js, returnByValue: true });
  ws.close();
  await fetch(`http://127.0.0.1:${PORT}/json/close/${t.id}`);
  const o = JSON.parse(r.result.value);
  o.http = bad.filter(x => !x.includes('email-decode'));
  o.fold = fold;
  return o;
}

let fails = 0;
for (const url of urls) {
  console.log('\n' + url);
  for (const [w, h] of SIZES) {
    const o = await measure(url, w, h);
    const flag = [];
    if (o.overflow) { flag.push(`OVERFLOW ${o.sw}>${o.cw} ${JSON.stringify(o.wide)}`); fails++; }
    if (o.broken) { flag.push(`${o.broken} BROKEN IMG`); fails++; }
    if (o.fallbackFont) { flag.push(`H1 FELL BACK TO ${o.h1px} SERIF (web font or CSS token missing)`); fails++; }
    if (o.fold && o.fold.missing) { flag.push(`FOLD selector ${FOLD} not found`); fails++; }
    else if (o.fold && o.fold.bottom > o.fold.vh) { flag.push(`BELOW FOLD: ${FOLD} bottom ${o.fold.bottom}px > ${o.fold.vh}px`); fails++; }
    if (o.http.length) { flag.push('HTTP ' + JSON.stringify(o.http.slice(0, 2))); fails++; }
    console.log(`  ${String(w).padStart(4)}x${h}  doc=${o.doc} imgs=${o.imgs}` +
      (o.iframe ? ` iframe@${o.iframe.t}/${o.iframe.h}px` : '') +
      (flag.length ? '  ** ' + flag.join(' | ') : '  ok'));
  }
}
console.log(fails ? `\n${fails} FAILURE(S)` : '\nall clean');
try { chrome.kill(); } catch (e) {}
process.exit(fails ? 1 : 0);
